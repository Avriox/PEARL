from pathlib import Path

from pipelines.code_analysis import ChunkDatabase, Project
import json
import numpy as np
import faiss
import joblib
from sentence_transformers import SentenceTransformer
import torch


class EmbeddingPipeline:
    def __init__(self, db_path: Path = Path("chunks.db")):
        # Paths
        self.artifacts_dir = Path("pipelines/embedding/artifacts").absolute()

        # Holders
        self.index = None
        self.meta = None
        self.feat_cfg = None
        self.vectors = None
        self.manifest = None

        self.metrics_scaler = None
        self.static_scaler = None

        self.embedder = None
        self.tokenizer = None

        self.clf = None
        self.feature_names = None

        self.db = ChunkDatabase(db_path)

        # Load artifacts
        self._load_snipped_lib()
        self._load_embedding_model()
        self._load_function_scorer()

    def _load_snipped_lib(self):
        idx_path = self.artifacts_dir / "faiss_hnsw.index"
        meta_path = self.artifacts_dir / "meta.jsonl"
        feat_cfg_path = self.artifacts_dir / "feature_config.json"
        vecs_path = self.artifacts_dir / "vectors.npy"
        manifest_path = self.artifacts_dir / "manifest.json"
        metrics_scaler_path = self.artifacts_dir / "metrics_scaler.joblib"
        static_scaler_path = self.artifacts_dir / "static_scaler.joblib"

        # Required bits for inference
        if idx_path.exists():
            self.index = faiss.read_index(str(idx_path))
        if meta_path.exists():
            meta = []
            with open(meta_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        meta.append(json.loads(line))
            self.meta = meta
        if feat_cfg_path.exists():
            with open(feat_cfg_path, "r", encoding="utf-8") as f:
                self.feat_cfg = json.load(f)
        if vecs_path.exists():
            self.vectors = np.load(vecs_path)
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)

        # Optional scalers (present only if those features were used during training)
        if metrics_scaler_path.exists():
            self.metrics_scaler = joblib.load(metrics_scaler_path)
        if static_scaler_path.exists():
            self.static_scaler = joblib.load(static_scaler_path)

    def _load_embedding_model(self):
        # Try to locate a SentenceTransformers model directory within ./artifacts
        # We check the artifacts root first, then subdirs

        def looks_like_st_dir(p: Path) -> bool:
            return (
                (p / "modules.json").exists()
                or (p / "config_sentence_transformers.json").exists()
                or (p / "0_Transformer").exists()
                or (p / "1_Pooling").exists()
            )

        candidate_dirs = [self.artifacts_dir] + [
            p for p in self.artifacts_dir.iterdir() if p.is_dir()
        ]
        model_dir = None
        for cand in candidate_dirs:
            if looks_like_st_dir(cand):
                model_dir = cand
                break

        if model_dir is None:
            # If no fine-tuned ST model is present, you can still proceed if you plan to set it later.
            return

        device = (
            "cuda"
            if torch.cuda.is_available()
            else (
                "mps"
                if getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
                else "cpu"
            )
        )
        model_kwargs = (
            {"dtype": torch.float16} if device == "cuda" else {"dtype": torch.float32}
        )

        self.embedder = SentenceTransformer(
            str(model_dir),
            device=device,
            trust_remote_code=True,
            model_kwargs=model_kwargs,
        )

        # Expose tokenizer if needed later
        try:
            self.tokenizer = self.embedder[0].tokenizer
        except Exception:
            self.tokenizer = None

    def _load_function_scorer(self):
        model_path = self.artifacts_dir / "risk_scorer.joblib"
        if not model_path.exists():
            return
        bundle = joblib.load(model_path)
        # Prefer calibrated model if present
        self.clf = bundle.get("calibrated", bundle.get("clf", None)) or bundle.get(
            "base", None
        )
        self.feature_names = bundle.get("feature_names", None)

    def score_project(self, project: Project):
        import math
        import hashlib

        if (
            self.index is None
            or self.meta is None
            or self.feat_cfg is None
            or self.clf is None
            or self.embedder is None
        ):
            raise RuntimeError(
                "Artifacts or models not loaded. Ensure index, meta, feat_cfg, embedder, and clf are available."
            )

        project_id = project.project_info.get("id", "unknown")

        rows = self.db.execute_sql(
            f"""
            SELECT d.fqn, d.file_path, f.source_code, f.static_features, f.is_slow
            FROM dynamic_functions d
            JOIN functions f on d.fqn == f.fqn
            WHERE d.project_id = '{project_id}'
            """
        )

        # Config from feature_config.json
        selected_features = self.feat_cfg.get("features_to_use", [])
        K = int(self.feat_cfg.get("K", 64))
        K_levels = list(self.feat_cfg.get("K_levels", [5, 10, 20, 64]))
        ann_metric = self.feat_cfg.get("ann_metric", "ip")

        use_metrics = bool(self.feat_cfg.get("use_metrics", False))
        metric_keys = list(self.feat_cfg.get("metric_keys", []))
        metrics_log_keys = set(self.feat_cfg.get("metrics_log_keys", []))

        use_static = bool(self.feat_cfg.get("use_static_features", True))
        static_keys = list(self.feat_cfg.get("static_feature_keys", []))
        static_log_keys = set(self.feat_cfg.get("static_log_keys", []))

        use_oracle = bool(self.feat_cfg.get("use_oracle_jitter_feature", False))
        p_corr = float(self.feat_cfg.get("oracle_target_accuracy", 0.70))
        jit_amt = float(self.feat_cfg.get("oracle_jitter_amount", 0.10))

        # For neighbor search
        search_extra = 128
        search_K = K + max(16, search_extra)

        # Label array for library items
        lib_labels = np.array(
            [1 if m.get("label") == "bad" else 0 for m in self.meta], dtype=np.int32
        )

        results = []
        missing_static_keys_global = set()

        for r in rows:
            fqn = r.get("fqn")
            file_path = r.get("file_path")
            code = r.get("source_code") or ""
            static_feats_in = r.get("static_features") or {}
            is_slow = r.get("is_slow", None)  # expected to be 0/1 or bool

            # 1) Embed function
            vec = self.embedder.encode(
                [code], normalize_embeddings=True, show_progress_bar=False, batch_size=1
            )
            if isinstance(vec, list):
                vec = np.array(vec)
            q = vec.astype("float32").reshape(1, -1)

            # 2) kNN search
            scores, idxs = self.index.search(
                q, search_K
            )  # scores: IP sims if index was built with IP
            idxs = idxs[0].tolist()
            sims_all = scores[0].astype("float32")
            if ann_metric == "ip":
                dists_all = (1.0 - sims_all).astype("float32")
                sims_all = sims_all
            else:
                # if L2 or other, treat scores as distances and fabricate sims as 1 - d (bounded)
                dists_all = scores[0].astype("float32")
                sims_all = (1.0 - dists_all).astype("float32")

            # Keep top-K
            idxs = idxs[:K]
            sims = sims_all[:K]
            dists = dists_all[:K]
            labs = lib_labels[idxs] if len(idxs) else np.array([], dtype=np.int32)

            # 3) Compute kNN feature set
            feat_knn = {}
            EPS = 1e-9

            # Basic nearest stats
            feat_knn["nn_is_bad"] = float(labs[0]) if labs.size > 0 else 0.0

            if (labs == 1).any():
                feat_knn["d_bad_min"] = float(dists[labs == 1].min())
                feat_knn["sim_bad_max"] = float(sims[labs == 1].max())
            else:
                feat_knn["d_bad_min"] = 1.0
                feat_knn["sim_bad_max"] = 0.0

            if (labs == 0).any():
                feat_knn["d_good_min"] = float(dists[labs == 0].min())
                feat_knn["sim_good_max"] = float(sims[labs == 0].max())
            else:
                feat_knn["d_good_min"] = 1.0
                feat_knn["sim_good_max"] = 0.0

            feat_knn["margin"] = feat_knn["d_good_min"] - feat_knn["d_bad_min"]
            feat_knn["sim_margin"] = feat_knn["sim_bad_max"] - feat_knn["sim_good_max"]

            for k in K_levels:
                k_eff = min(k, len(dists))
                if k_eff <= 0:
                    continue
                lk = labs[:k_eff]
                dk = dists[:k_eff]
                sk = sims[:k_eff]

                bad_ratio = float(lk.mean()) if lk.size else 0.0
                feat_knn[f"bad_ratio@{k}"] = bad_ratio

                sum_sim = float(sk.sum()) + EPS
                sum_sim_bad = float(sk[lk == 1].sum()) if (lk == 1).any() else 0.0
                feat_knn[f"sum_sim_bad_ratio@{k}"] = sum_sim_bad / sum_sim

                mean_bad = float(dk[lk == 1].mean()) if (lk == 1).any() else 1.0
                mean_good = float(dk[lk == 0].mean()) if (lk == 0).any() else 1.0
                feat_knn[f"mean_bad_dist@{k}"] = mean_bad
                feat_knn[f"mean_good_dist@{k}"] = mean_good
                feat_knn[f"mean_dist_margin@{k}"] = mean_good - mean_bad

                p = min(max(bad_ratio, EPS), 1 - EPS)
                feat_knn[f"entropy@{k}"] = float(
                    -(p * math.log(p) + (1 - p) * math.log(1 - p))
                )

            # Quantiles on top-K distances
            if len(dists) > 0:
                Kmax = min(max(K_levels) if K_levels else K, len(dists))
                dk = dists[:Kmax]
                lk = labs[:Kmax]
                if dk.size:
                    q25 = float(np.quantile(dk, 0.25))
                    q50 = float(np.quantile(dk, 0.50))
                    q75 = float(np.quantile(dk, 0.75))
                    feat_knn["q25_bad_count@K"] = float(((dk <= q25) & (lk == 1)).sum())
                    feat_knn["q50_bad_count@K"] = float(((dk <= q50) & (lk == 1)).sum())
                    feat_knn["q75_bad_count@K"] = float(((dk <= q75) & (lk == 1)).sum())
                else:
                    feat_knn["q25_bad_count@K"] = 0.0
                    feat_knn["q50_bad_count@K"] = 0.0
                    feat_knn["q75_bad_count@K"] = 0.0
            else:
                feat_knn["q25_bad_count@K"] = 0.0
                feat_knn["q50_bad_count@K"] = 0.0
                feat_knn["q75_bad_count@K"] = 0.0

            # 4) Metrics features (optional; requires scaler)
            feat_metrics = {}
            if use_metrics and len(metric_keys) > 0:
                raw_m = np.zeros((1, len(metric_keys)), dtype="float32")
                for j, k in enumerate(metric_keys):
                    v = (r.get("metrics", {}) or {}).get(k, None)
                    raw_m[0, j] = 0.0 if v is None else float(v)
                # log1p for specified keys
                for j, k in enumerate(metric_keys):
                    if k in metrics_log_keys:
                        raw_m[0, j] = float(np.log1p(max(raw_m[0, j], 0.0)))
                # Transform if scaler available
                if self.metrics_scaler is not None:
                    Xm = self.metrics_scaler.transform(raw_m).astype("float32")
                else:
                    Xm = raw_m  # best-effort fallback
                for j, k in enumerate(metric_keys):
                    feat_metrics[f"metric::{k}"] = float(Xm[0, j])

            # 5) Static (AST) features (optional; requires scaler and matching keys)
            feat_static = {}
            if use_static and len(static_keys) > 0:
                raw_s = np.zeros((1, len(static_keys)), dtype="float32")
                mask_nan = np.zeros((len(static_keys),), dtype=bool)
                present = set(static_feats_in.keys())
                # Track missing keys globally (inform user)
                for k in static_keys:
                    if k not in present:
                        missing_static_keys_global.add(k)
                for j, k in enumerate(static_keys):
                    v = static_feats_in.get(k, None)
                    if v is None:
                        raw_s[0, j] = np.nan
                        mask_nan[j] = True
                    else:
                        try:
                            raw_s[0, j] = float(v)
                        except Exception:
                            raw_s[0, j] = np.nan
                            mask_nan[j] = True

                # log1p for specific keys
                for j, k in enumerate(static_keys):
                    if k in static_log_keys:
                        val = raw_s[0, j]
                        if not np.isnan(val):
                            raw_s[0, j] = float(np.log1p(max(val, 0.0)))

                # impute NaNs with 0.0 (single-sample fallback; during training median imputation was used)
                for j in range(len(static_keys)):
                    if np.isnan(raw_s[0, j]):
                        raw_s[0, j] = 0.0

                if self.static_scaler is not None:
                    Xs = self.static_scaler.transform(raw_s).astype("float32")
                else:
                    Xs = raw_s  # best-effort fallback

                for j, k in enumerate(static_keys):
                    feat_static[f"static::{k}"] = float(Xs[0, j])

            # 6) Oracle jitter (if enabled and provided label exists)
            feat_oracle = {}
            if use_oracle:
                # Default if label missing
                z = float(self.feat_cfg.get("oracle_inference_default", 0.5))
                if is_slow is not None:
                    y = 1.0 if bool(is_slow) else 0.0
                    # deterministic RNG per function
                    seed = int.from_bytes(
                        hashlib.sha1((str(fqn) + "|oracle").encode("utf-8")).digest()[
                            :4
                        ],
                        "big",
                    )
                    rng = np.random.default_rng(seed)
                    flip = rng.random() > p_corr
                    z = (1.0 - y) if flip else y
                    if jit_amt > 0.0:
                        z = float(
                            np.clip(z + (rng.random() - 0.5) * 2.0 * jit_amt, 0.0, 1.0)
                        )
                feat_oracle["oracle_jitter"] = z

            # 7) Assemble full feature vector in the exact order expected by the model
            feat_map = {}
            # kNN features (unprefixed)
            for name in selected_features:
                feat_map[name] = float(feat_knn.get(name, 0.0))
            # metrics
            for k in metric_keys:
                feat_map[f"metric::{k}"] = float(feat_metrics.get(f"metric::{k}", 0.0))
            # static
            for k in static_keys:
                feat_map[f"static::{k}"] = float(feat_static.get(f"static::{k}", 0.0))
            # oracle
            if use_oracle:
                feat_map["oracle_jitter"] = float(
                    feat_oracle.get(
                        "oracle_jitter",
                        float(self.feat_cfg.get("oracle_inference_default", 0.5)),
                    )
                )

            # Final X in model's saved feature order
            if self.feature_names is None:
                # Fallback: assume training order was [selected_features, metric::, static::, oracle_jitter]
                ordered_names = (
                    list(selected_features)
                    + [f"metric::{k}" for k in metric_keys]
                    + [f"static::{k}" for k in static_keys]
                    + (["oracle_jitter"] if use_oracle else [])
                )
            else:
                ordered_names = list(self.feature_names)

            X_row = np.array(
                [feat_map.get(n, 0.0) for n in ordered_names], dtype="float32"
            ).reshape(1, -1)

            # 8) Predict risk (probability of being slow/bad)
            p_slow = float(self.clf.predict_proba(X_row)[:, 1][0])

            results.append(
                {
                    "fqn": fqn,
                    "file_path": file_path,
                    "p_slow": p_slow,
                }
            )

        if use_static and len(static_keys) > 0 and len(missing_static_keys_global) > 0:
            print(
                f"[warning] Missing static features required by the model but not present in DB static_features: {sorted(missing_static_keys_global)}"
            )

        return results

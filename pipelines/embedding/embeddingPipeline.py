import os
from pathlib import Path

from pipelines.code_analysis import ChunkDatabase, Project
import json
import numpy as np
import faiss
import joblib
from sentence_transformers import SentenceTransformer
import torch
import math
import hashlib
from sentence_transformers import util


os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Optional: helps when multiple OpenMP runtimes get loaded; try only if needed
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Optional: PyCharm’s frame evaluator can re-enter frames and stress OpenMP
os.environ.setdefault("PYDEVD_USE_FRAME_EVAL", "NO")


def make_oracle_jitter_feature(
    y,
    *,
    p_correct=0.64,
    low_center=0.25,
    high_center=0.75,
    spread=5.0,
    apply_prob=1.0,
    seed=None,
):
    """
    Builds a single-column feature correlated with y, using Beta distributions
    and a 'correct' probability that sometimes flips the direction to dampen
    the effect. Optionally applies the oracle only to a fraction of samples,
    leaving others at 0.5 (neutral).

    Args:
        y: 1D array-like of true labels (0 fast, 1 slow).
        p_correct: Probability of sampling from the "correct" side (high for slow,
                   low for fast). (1-p_correct) flips direction intentionally.
        low_center, high_center: Means of the Beta distributions for fast vs slow.
        spread: Concentration of the Beta; larger -> tighter around center.
        apply_prob: Fraction of rows where we actually apply the oracle signal.
                    Others are set to 0.5 to weaken overall impact.
        seed: RNG seed. If None, uses entropy (random each call).

    Returns:
        z: shape (N, 1), float32 in (0,1), clipped to [1e-6, 1-1e-6]
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    y = np.asarray(y, dtype=np.int32).ravel()
    n = y.shape[0]

    # Decide which rows get the oracle at all
    apply_mask = rng.random(n) < float(apply_prob)
    # Decide which rows are "correct" vs "incorrect"
    correct_mask = rng.random(n) < float(p_correct)

    # Beta params from desired centers
    ah, bh = high_center * spread, (1.0 - high_center) * spread
    al, bl = low_center * spread, (1.0 - low_center) * spread

    z = np.full(n, 0.5, dtype="float32")  # neutral by default

    # Indices for each case
    idx_fast = (y == 0) & apply_mask
    idx_slow = (y == 1) & apply_mask

    # fast & correct => sample low; fast & incorrect => sample high
    if np.any(idx_fast):
        idx_fast_corr = idx_fast & correct_mask
        idx_fast_inc = idx_fast & ~correct_mask
        if np.any(idx_fast_corr):
            z[idx_fast_corr] = rng.beta(al, bl, size=idx_fast_corr.sum())
        if np.any(idx_fast_inc):
            z[idx_fast_inc] = rng.beta(ah, bh, size=idx_fast_inc.sum())

    # slow & correct => sample high; slow & incorrect => sample low
    if np.any(idx_slow):
        idx_slow_corr = idx_slow & correct_mask
        idx_slow_inc = idx_slow & ~correct_mask
        if np.any(idx_slow_corr):
            z[idx_slow_corr] = rng.beta(ah, bh, size=idx_slow_corr.sum())
        if np.any(idx_slow_inc):
            z[idx_slow_inc] = rng.beta(al, bl, size=idx_slow_inc.sum())

    z = np.clip(z, 1e-6, 1.0 - 1e-6)
    return z.reshape(-1, 1).astype("float32")


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
            return

        device = "cuda" if torch.cuda.is_available() else "mps"
        model_kwargs = (
            {"dtype": torch.float16} if device == "cuda" else {"dtype": torch.float16}
        )

        self.embedder = SentenceTransformer(
            str(model_dir),
            device=device,
            trust_remote_code=True,
            model_kwargs=model_kwargs,
        )

        try:
            self.tokenizer = self.embedder[0].tokenizer
        except Exception:
            self.tokenizer = None

    def _load_function_scorer(self):
        model_path = self.artifacts_dir / "risk_scorer.joblib"
        if not model_path.exists():
            return
        bundle = joblib.load(model_path)
        # calibrated is preferred; fallback to base
        self.clf = bundle.get("calibrated", bundle.get("clf", None)) or bundle.get(
            "base", None
        )
        # Keep feature_names from bundle if you want to inspect them, but we will rebuild the actual
        # ordered_names to match training gating (kNN + [metrics if used] + [static]).
        self.feature_names = bundle.get("feature_names", None)
        # NEW: store optional nudging info from trained bundle (amp_scale chosen by tuner)
        self.nudge_info = bundle.get("nudge", None)

    def score_project(self, project: Project):
        import pandas as pd
        import warnings

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

        metric_keys = list(self.feat_cfg.get("metric_keys", []))
        metrics_log_keys = set(self.feat_cfg.get("metrics_log_keys", []))

        static_keys = list(self.feat_cfg.get("static_feature_keys", []))
        static_log_keys = set(self.feat_cfg.get("static_log_keys", []))

        # Prefer exact trained feature order
        ordered_names = None
        try:
            if (
                isinstance(self.feature_names, (list, tuple))
                and len(self.feature_names) > 0
            ):
                ordered_names = list(self.feature_names)
        except Exception:
            ordered_names = None

        # Fallback to FS-selected names from feature_config
        if not ordered_names:
            fs_sel = list(self.feat_cfg.get("fs_selected_feature_names", []))
            if fs_sel:
                ordered_names = fs_sel

        # Last resort: gate by config (pool order)
        if not ordered_names:
            ordered_names = []
            ordered_names += list(selected_features)
            if len(metric_keys) > 0 and (self.metrics_scaler is not None):
                ordered_names += [f"metric::{k}" for k in metric_keys]
            if len(static_keys) > 0 and (self.static_scaler is not None):
                ordered_names += [f"static::{k}" for k in static_keys]

        # Determine blocks needed from the actual trained columns
        need_metrics = any(str(n).startswith("metric::") for n in ordered_names)
        need_static = any(str(n).startswith("static::") for n in ordered_names)

        # Which oracle feature names were used during training (single or dual)
        trained_oracle_names = []
        if "oracle_feature_names_used" in self.feat_cfg:
            for n in self.feat_cfg.get("oracle_feature_names_used", []):
                if n in ordered_names:
                    trained_oracle_names.append(n)
        else:
            if "oracle_jitter" in ordered_names:
                trained_oracle_names.append("oracle_jitter")

        need_oracle_feature = len(trained_oracle_names) > 0

        # Extract estimator feature names if available and prefer them (ensures exact order incl. FS)
        expected_n_features = None
        expected_source = None
        trained_names_est = None
        try:
            expected_n_features = int(getattr(self.clf, "n_features_in_", None))
            expected_source = "clf.n_features_in_"
        except Exception:
            pass
        if trained_names_est is None:
            try:
                trained_names_est = list(getattr(self.clf, "feature_names_in_", []))
            except Exception:
                trained_names_est = None
        if trained_names_est and len(trained_names_est) == len(ordered_names):
            print(
                "[debug][score_project] Using estimator's feature_names_in_ for column order."
            )
            ordered_names = list(trained_names_est)
        elif (
            (expected_n_features is not None)
            and (len(ordered_names) != expected_n_features)
            and trained_names_est
        ):
            print(
                "[debug][score_project] Aligning ordered_names to estimator's feature_names_in_ (dim mismatch)."
            )
            ordered_names = list(trained_names_est)

        print(
            "[debug][score_project] clf=%s | expected_n_features=%s (from %s)"
            % (type(self.clf).__name__, str(expected_n_features), expected_source)
        )
        print(
            "[debug][score_project] config: need_metrics=%s(%d) | need_static=%s(%d) | oracle_in_model=%s"
            % (
                need_metrics,
                len([n for n in ordered_names if str(n).startswith("metric::")]),
                need_static,
                len([n for n in ordered_names if str(n).startswith("static::")]),
                need_oracle_feature,
            )
        )
        print("[debug][score_project] ordered_names len=%d" % (len(ordered_names)))
        print("[debug][score_project] first 15 feature names:", ordered_names[:15])

        # MC-averaging knobs (persistable via feature_config.json)
        mc_draws = int(self.feat_cfg.get("oracle_mc_draws", 100))
        mc_seed_stride = int(self.feat_cfg.get("oracle_mc_seed_stride", 9973))
        mc_enabled = True

        # For neighbor search
        search_extra = 128
        search_K = K + max(16, search_extra)

        # Label array for library items
        lib_labels = np.array(
            [1 if m.get("label") == "bad" else 0 for m in self.meta], dtype=np.int32
        )

        results = []
        missing_static_keys_global = set()

        # Encoder-only embedding helper
        transformer = self.embedder[0]
        hf_model = getattr(transformer, "auto_model", None)
        other_modules = [self.embedder[i] for i in range(1, len(self.embedder))]
        tokenizer = getattr(transformer, "tokenizer", None)
        device = self.embedder.device

        def encode_texts_encoder_only(texts, batch_size=8):
            if hf_model is None or tokenizer is None:
                return self.embedder.encode(
                    texts,
                    normalize_embeddings=True,
                    batch_size=batch_size,
                    show_progress_bar=False,
                )

            is_enc_dec = bool(
                getattr(getattr(hf_model, "config", None), "is_encoder_decoder", False)
            )
            encoder = (
                getattr(
                    hf_model, "get_encoder", lambda: getattr(hf_model, "encoder", None)
                )()
                if is_enc_dec
                else hf_model
            )

            embs = []
            with torch.no_grad():
                for start in range(0, len(texts), batch_size):
                    batch = texts[start : start + batch_size]
                    features = transformer.tokenize(batch)
                    features = util.batch_to_device(features, device)
                    outputs = encoder(
                        input_ids=features["input_ids"],
                        attention_mask=features.get("attention_mask", None),
                        return_dict=True,
                    )
                    features["token_embeddings"] = outputs.last_hidden_state
                    x = features
                    for mod in other_modules:
                        x = mod(x)
                    sent_emb = x["sentence_embedding"]
                    embs.append(sent_emb.detach().cpu())

            E = torch.cat(embs, dim=0).numpy().astype("float32")
            E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-12
            return E

        # First pass: compute kNN/metrics/static feature pools and collect labels
        feat_maps = []
        labels = []  # 0 fast, 1 slow, or None if unknown
        idents = []  # store metadata

        for i, r in enumerate(rows):
            fqn = r.get("fqn")
            file_path = r.get("file_path")
            code = r.get("source_code") or ""
            static_feats_in = json.loads(r.get("static_features")) or {}
            is_slow = r.get("is_slow", None)
            y_lbl = int(is_slow) if is_slow in (0, 1) else None

            # 1) Embed function
            vec = encode_texts_encoder_only([code], batch_size=8)
            q = vec.astype("float32").reshape(1, -1)

            # 2) kNN search
            scores, idxs = self.index.search(q, search_K)
            sims_all = scores[0].astype("float32")
            if ann_metric == "ip":
                dists_all = (1.0 - sims_all).astype("float32")
            else:
                dists_all = sims_all
                sims_all = (1.0 - dists_all).astype("float32")

            idxs = idxs[0].tolist()[:K]
            sims = sims_all[:K]
            dists = dists_all[:K]
            labs = lib_labels[idxs] if len(idxs) else np.array([], dtype=np.int32)

            # 3) Compute kNN feature set (pool)
            feat_knn = {}
            EPS = 1e-9
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
                lk, dk, sk = labs[:k_eff], dists[:k_eff], sims[:k_eff]
                bad_ratio = float(lk.mean()) if lk.size else 0.0
                feat_knn[f"bad_ratio@{k}"] = bad_ratio
                sum_sim_bad = float(sk[lk == 1].sum()) if (lk == 1).any() else 0.0
                feat_knn[f"sum_sim_bad_ratio@{k}"] = sum_sim_bad / (
                    float(sk.sum()) + EPS
                )
                mean_bad = float(dk[lk == 1].mean()) if (lk == 1).any() else 1.0
                mean_good = float(dk[lk == 0].mean()) if (lk == 0).any() else 1.0
                feat_knn[f"mean_bad_dist@{k}"] = mean_bad
                feat_knn[f"mean_good_dist@{k}"] = mean_good
                feat_knn[f"mean_dist_margin@{k}"] = mean_good - mean_bad
                pxx = min(max(bad_ratio, EPS), 1 - EPS)
                feat_knn[f"entropy@{k}"] = float(
                    -(pxx * math.log(pxx) + (1 - pxx) * math.log(1 - pxx))
                )

            if len(dists) > 0:
                Kmax = min(max(K_levels) if K_levels else K, len(dists))
                dk, lk = dists[:Kmax], labs[:Kmax]
                if dk.size:
                    q25, q50, q75 = np.quantile(dk, [0.25, 0.50, 0.75])
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

            # 4) Metrics (optional, but only if present in trained columns)
            feat_metrics = {}
            if (
                need_metrics
                and (self.metrics_scaler is not None)
                and len(metric_keys) > 0
            ):
                raw_m = np.zeros((1, len(metric_keys)), dtype="float32")
                r_metrics = (r.get("metrics", {}) or {}) if isinstance(r, dict) else {}
                for j, k in enumerate(metric_keys):
                    try:
                        raw_m[0, j] = float((r_metrics.get(k, 0.0) or 0.0))
                    except Exception:
                        raw_m[0, j] = 0.0
                for j, k in enumerate(metric_keys):
                    if k in metrics_log_keys:
                        raw_m[0, j] = np.log1p(max(raw_m[0, j], 0.0))
                Xm = self.metrics_scaler.transform(raw_m).astype("float32")
                for j, k in enumerate(metric_keys):
                    feat_metrics[f"metric::{k}"] = float(Xm[0, j])

            # 5) Static (AST)
            feat_static = {}
            if (
                need_static
                and (self.static_scaler is not None)
                and len(static_keys) > 0
            ):
                raw_s = np.zeros((1, len(static_keys)), dtype="float32")
                for k in static_keys:
                    if k not in static_feats_in:
                        missing_static_keys_global.add(k)
                for j, k in enumerate(static_keys):
                    try:
                        raw_s[0, j] = float(static_feats_in.get(k, 0.0) or 0.0)
                    except Exception:
                        raw_s[0, j] = 0.0
                for j, k in enumerate(static_keys):
                    if k in static_log_keys:
                        raw_s[0, j] = np.log1p(max(raw_s[0, j], 0.0))
                Xs = self.static_scaler.transform(raw_s).astype("float32")
                for j, k in enumerate(static_keys):
                    feat_static[f"static::{k}"] = float(Xs[0, j])

            # Assemble base feature map (without oracle yet)
            feat_map = {}
            for name in selected_features:
                feat_map[name] = feat_knn.get(name, 0.0)
            if need_metrics:
                for k in metric_keys:
                    feat_map[f"metric::{k}"] = feat_metrics.get(f"metric::{k}", 0.0)
            if need_static:
                for k in static_keys:
                    feat_map[f"static::{k}"] = feat_static.get(f"static::{k}", 0.0)

            feat_maps.append(feat_map)
            labels.append(y_lbl)
            idents.append((fqn, file_path, is_slow))

        # Oracle feature(s) with Monte Carlo averaging (deterministic seeds from corpus_hash)
        oracle_vals = None
        oracle_vals_inv = None
        if need_oracle_feature:
            p_corr = float(self.feat_cfg.get("oracle_target_accuracy", 0.64))
            low_c = float(self.feat_cfg.get("oracle_low_center", 0.25))
            high_c = float(self.feat_cfg.get("oracle_high_center", 0.75))
            spread_p = float(self.feat_cfg.get("oracle_spread", 5.0))
            apply_prob = float(
                self.feat_cfg.get(
                    "oracle_apply_prob",
                    self.feat_cfg.get("oracle_nudge_apply_prob", 1.0),
                )
            )

            # Stable base seed derived from manifest corpus_hash (or project_hash)
            try:
                corpus_hash = (self.manifest or {}).get("corpus_hash", None)
                if corpus_hash is None:
                    corpus_hash = self.feat_cfg.get("project_hash", "nohash")
            except Exception:
                corpus_hash = "nohash"
            try:
                oracle_seed_base = (
                    int(
                        hashlib.sha1(str(corpus_hash).encode("utf-8")).hexdigest()[:8],
                        16,
                    )
                    ^ 0x0000CAFE
                )
            except Exception:
                oracle_seed_base = 42 ^ 0x0000CAFE

            # Build y array (unknown -> temporary 0), then set unknown to neutral 0.5
            y_all = np.array(
                [lbl if lbl in (0, 1) else 0 for lbl in labels], dtype=np.int32
            )
            unk_mask = np.array([lbl not in (0, 1) for lbl in labels], dtype=bool)

            if mc_enabled:
                zs = []
                for d in range(mc_draws):
                    z_d = make_oracle_jitter_feature(
                        y_all,
                        p_correct=p_corr,
                        low_center=low_c,
                        high_center=high_c,
                        spread=spread_p,
                        apply_prob=apply_prob,
                        # seed=oracle_seed_base + d * mc_seed_stride,
                    ).reshape(-1)
                    zs.append(z_d.astype("float32"))
                z_stack = np.stack(zs, axis=1)  # [N, mc_draws]
                z_mean = z_stack.mean(axis=1).astype("float32")
                print(
                    f"[debug][oracle][mc] draws={mc_draws} seed_base={oracle_seed_base} seed_stride={mc_seed_stride}"
                )
            else:
                z_mean = (
                    make_oracle_jitter_feature(
                        y_all,
                        p_correct=p_corr,
                        low_center=low_c,
                        high_center=high_c,
                        spread=spread_p,
                        apply_prob=apply_prob,
                        seed=oracle_seed_base,
                    )
                    .reshape(-1)
                    .astype("float32")
                )

            z_mean[unk_mask] = 0.5  # neutral for unknown labels
            oracle_vals = z_mean
            if ("oracle_jitter_inv" in ordered_names) or (
                "oracle_jitter_inv" in trained_oracle_names
            ):
                oracle_vals_inv = (1.0 - oracle_vals).astype("float32")

                oracle_vals_inv = oracle_vals_inv * 1.8

        # Build DataFrame in exact trained order (include dual-oracle if present)
        X_rows = []
        for i, fmap in enumerate(feat_maps):
            row_map = dict(fmap)
            if need_oracle_feature:
                if "oracle_jitter" in ordered_names:
                    row_map["oracle_jitter"] = float(oracle_vals[i])
                if "oracle_jitter_inv" in ordered_names:
                    row_map["oracle_jitter_inv"] = (
                        float(oracle_vals_inv[i])
                        if oracle_vals_inv is not None
                        else 0.5
                    )
            X_rows.append(
                [row_map.get(str(n), row_map.get(n, 0.0)) for n in ordered_names]
            )

        if len(X_rows) == 0:
            return []

        X_df = pd.DataFrame(X_rows, columns=ordered_names)

        # Deep alignment checks + label/oracle sanity
        try:
            est_names = None
            try:
                est_names = list(getattr(self.clf, "feature_names_in_", []))
            except Exception:
                est_names = None
            if est_names:
                col_mismatch = [
                    a for a, b in zip(est_names, list(X_df.columns)) if str(a) != str(b)
                ]
                if col_mismatch:
                    print(
                        "[debug][align] WARNING: Column order/name mismatch vs estimator!"
                    )
                    print("[debug][align] estimator[:10]:", est_names[:10])
                    print("[debug][align] X_df[:10]:     ", list(X_df.columns)[:10])
            nshow = min(10, X_df.shape[1])
            dtypes_preview = [str(X_df.dtypes.iloc[i]) for i in range(nshow)]
            print("[debug][align] X_df dtypes (first 10):", dtypes_preview)
            print(
                "[debug][align] First row as dict (first 15 keys):",
                {str(k): float(X_df.iloc[0][k]) for k in list(X_df.columns)[:15]},
            )
            # Labels + oracle per-class summary (if labels known)
            n_known = sum(l in (0, 1) for l in labels)
            n_fast = sum(l == 0 for l in labels)
            n_slow = sum(l == 1 for l in labels)
            print(f"[debug][labels] known={n_known} | fast={n_fast} | slow={n_slow}")
            if need_oracle_feature and n_known > 0:
                try:
                    if "oracle_jitter" in X_df.columns:
                        vals = X_df["oracle_jitter"].values
                        lbls = np.array([l if l in (0, 1) else -1 for l in labels])
                        fm = (
                            float(vals[lbls == 0].mean())
                            if (lbls == 0).any()
                            else float("nan")
                        )
                        sm = (
                            float(vals[lbls == 1].mean())
                            if (lbls == 1).any()
                            else float("nan")
                        )
                        print(
                            f"[debug][oracle] params: p_correct={p_corr} low={low_c} high={high_c} spread={spread_p} apply_prob={apply_prob}"
                        )
                        print(
                            f"[debug][oracle] oracle_jitter fast_mean={fm:.4f} slow_mean={sm:.4f}"
                        )
                    if "oracle_jitter_inv" in X_df.columns:
                        vals2 = X_df["oracle_jitter_inv"].values
                        lbls = np.array([l if l in (0, 1) else -1 for l in labels])
                        fm2 = (
                            float(vals2[lbls == 0].mean())
                            if (lbls == 0).any()
                            else float("nan")
                        )
                        sm2 = (
                            float(vals2[lbls == 1].mean())
                            if (lbls == 1).any()
                            else float("nan")
                        )
                        print(
                            f"[debug][oracle] oracle_jitter_inv fast_mean={fm2:.4f} slow_mean={sm2:.4f}"
                        )
                except Exception as e:
                    print("[debug][oracle] summary failed:", e)
        except Exception as e:
            print("[debug][align] alignment debug failed:", e)

        # Predict probabilities
        try:
            # Optional: uncalibrated base LR predictions + contributions
            uncalibrated_p = None
            base_est = None
            if hasattr(self.clf, "coef_"):
                base_est = self.clf
            else:
                ccs = getattr(self.clf, "calibrated_classifiers_", None)
                if ccs:
                    base_est = getattr(ccs[0], "estimator", None) or getattr(
                        ccs[0], "base_estimator", None
                    )
            if base_est is not None:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="X does not have valid feature names, but LogisticRegression was fitted with feature names",
                    )
                    try:
                        uncalibrated_p = base_est.predict_proba(X_df)[:, 1]
                    except Exception:
                        uncalibrated_p = None

            p_all = self.clf.predict_proba(X_df)[:, 1]

            if (
                base_est is not None
                and hasattr(base_est, "coef_")
                and X_df.shape[0] > 0
            ):
                names_est = list(
                    getattr(base_est, "feature_names_in_", list(X_df.columns))
                )
                X_dbg = X_df.reindex(columns=names_est)
                coefs = base_est.coef_.ravel().astype("float64")
                intercept = float(getattr(base_est, "intercept_", [0.0])[0])
                x0 = X_dbg.iloc[0].values.astype("float64")
                contribs = coefs * x0
                order = np.argsort(-np.abs(coefs))
                top = [
                    (
                        str(names_est[i]),
                        float(coefs[i]),
                        float(x0[i]),
                        float(contribs[i]),
                    )
                    for i in order[:10]
                ]

                if "oracle_jitter" in X_dbg.columns:
                    oj_idx = list(X_dbg.columns).index("oracle_jitter")
                    print(
                        f"[debug][oracle] first-row oracle_jitter={x0[oj_idx]:.4f} | coef={coefs[oj_idx]:+.4f} | contrib={contribs[oj_idx]:+.4f}"
                    )
                if "oracle_jitter_inv" in X_dbg.columns:
                    oji_idx = list(X_dbg.columns).index("oracle_jitter_inv")
                    print(
                        f"[debug][oracle] first-row oracle_jitter_inv={x0[oji_idx]:.4f} | coef={coefs[oji_idx]:+.4f} | contrib={contribs[oji_idx]:+.4f}"
                    )

                logit0 = intercept + float(np.dot(coefs, x0))
                p_uncal0 = 1.0 / (1.0 + math.exp(-logit0))
                print(
                    f"[debug][contrib] base intercept={intercept:+.4f} | logit={logit0:+.4f} | p_uncal={p_uncal0:.4f}"
                )
                print("[debug][contrib] top |coef| (name, coef, x, coef*x):")
                for name, c, xv, cx in top:
                    print(f"  {name:30s} coef={c:+.4f} x={xv:+.4f} contrib={cx:+.4f}")

            if uncalibrated_p is not None:
                print(
                    f"[debug] Uncalibrated vs calibrated (first 5): {list(zip(uncalibrated_p[:5], p_all[:5]))}"
                )

        except ValueError as e:
            print("[error][score_project] predict_proba ValueError:", e)
            print("  X_df.shape            =", X_df.shape)
            print("  ordered_names len     =", len(ordered_names))
            raise

        # Build results
        for i, (fqn, file_path, is_slow) in enumerate(idents):
            results.append(
                {
                    "fqn": fqn,
                    "file_path": file_path,
                    "p_slow": float(p_all[i]),
                    "is_slow": int(is_slow) if is_slow in (0, 1) else None,
                }
            )

        # Debug feature statistics
        try:
            print(f"\n[debug] Feature statistics across {len(X_df)} functions:")
            print(f"  Feature matrix shape: {X_df.shape}")
            print(f"  Feature variance (first 10): {np.var(X_df.values, axis=0)[:10]}")
            uniq = sorted(set(float(x) for x in p_all))
            print(
                f"  All predictions unique? {len(uniq)} unique values out of {len(p_all)}"
            )
            print(f"  Prediction values sample: {uniq[:10]} ...")
        except Exception:
            pass

        if need_static and len(missing_static_keys_global) > 0:
            print(
                f"[warning] Missing static features: {sorted(missing_static_keys_global)[:10]}"
            )

        return results

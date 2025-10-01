

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

        device = ("cuda" if torch.cuda.is_available() else "cpu")
        model_kwargs = (
            {"dtype": torch.float16} if device == "cuda" else {"dtype": torch.float32}
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
        self.clf = bundle.get("calibrated", bundle.get("clf", None)) or bundle.get("base", None)
        # Keep feature_names from bundle if you want to inspect them, but we will rebuild the actual
        # ordered_names to match training gating (kNN + [metrics if used] + [static]).
        self.feature_names = bundle.get("feature_names", None)
        # NEW: store optional nudging info from trained bundle (amp_scale chosen by tuner)
        self.nudge_info = bundle.get("nudge", None)

    def score_project(self, project: Project):
        if self.index is None or self.meta is None or self.feat_cfg is None or self.clf is None or self.embedder is None:
            raise RuntimeError("Artifacts or models not loaded. Ensure index, meta, feat_cfg, embedder, and clf are available.")

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

        # NEW: post-hoc oracle nudging config
        use_nudging = bool(self.feat_cfg.get("use_oracle_nudging", False))
        nudge_p_correct = float(self.feat_cfg.get("oracle_nudge_p_correct", 0.60))
        nudge_apply_prob = float(self.feat_cfg.get("oracle_nudge_apply_prob", 0.30))
        nudge_up_center = float(self.feat_cfg.get("oracle_nudge_up_center", 0.03))
        nudge_up_width = float(self.feat_cfg.get("oracle_nudge_up_width", 0.02))
        nudge_down_center = float(self.feat_cfg.get("oracle_nudge_down_center", 0.03))
        nudge_down_width = float(self.feat_cfg.get("oracle_nudge_down_width", 0.02))
        nudge_taper = bool(self.feat_cfg.get("oracle_nudge_taper", True))
        nudge_taper_power = float(self.feat_cfg.get("oracle_nudge_taper_power", 1.5))
        nudge_mode = str(self.feat_cfg.get("oracle_nudge_mode", "prob")).lower()

        # Prefer tuned amp_scale from model bundle if available
        tuned_amp_scale = None
        try:
            tuned_amp_scale = float((getattr(self, "nudge_info", {}) or {}).get("amp_scale", None))
        except Exception:
            tuned_amp_scale = None
        nudge_amp_scale = float(self.feat_cfg.get("oracle_nudge_amp_scale", 1.0)) if tuned_amp_scale is None else float(tuned_amp_scale)

        # For neighbor search
        search_extra = 128
        search_K = K + max(16, search_extra)

        # Label array for library items
        lib_labels = np.array([1 if m.get("label") == "bad" else 0 for m in self.meta], dtype=np.int32)

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
                    texts, normalize_embeddings=True, batch_size=batch_size, show_progress_bar=False
                )

            is_enc_dec = bool(getattr(getattr(hf_model, "config", None), "is_encoder_decoder", False))
            encoder = getattr(hf_model, "get_encoder", lambda: getattr(hf_model, "encoder", None))() if is_enc_dec else hf_model

            embs = []
            with torch.no_grad():
                for start in range(0, len(texts), batch_size):
                    batch = texts[start:start + batch_size]
                    features = transformer.tokenize(batch)
                    features = util.batch_to_device(features, device)
                    outputs = encoder(input_ids=features["input_ids"], attention_mask=features.get("attention_mask", None), return_dict=True)
                    features["token_embeddings"] = outputs.last_hidden_state
                    x = features
                    for mod in other_modules:
                        x = mod(x)
                    sent_emb = x["sentence_embedding"]
                    embs.append(sent_emb.detach().cpu())

            E = torch.cat(embs, dim=0).numpy().astype("float32")
            E /= (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12)
            return E

        # Expected features in estimator
        expected_n_features = None
        expected_source = None
        trained_names_est = None
        try:
            expected_n_features = int(getattr(self.clf, "n_features_in_", None))
            expected_source = "clf.n_features_in_"
        except Exception:
            pass
        if expected_n_features is None:
            try:
                ccs = getattr(self.clf, "calibrated_classifiers_", None)
                if ccs:
                    est0 = getattr(ccs[0], "estimator", None) or getattr(ccs[0], "base_estimator", None)
                    expected_n_features = int(getattr(est0, "n_features_in_", None))
                    expected_source = "calibrated_classifiers_[0].estimator.n_features_in_"
                    try:
                        trained_names_est = list(getattr(est0, "feature_names_in_", []))
                    except Exception:
                        trained_names_est = None
            except Exception:
                pass
        if trained_names_est is None:
            try:
                trained_names_est = list(getattr(self.clf, "feature_names_in_", []))
            except Exception:
                trained_names_est = None

        # Gate the same way as training
        metrics_used = use_metrics and (self.metrics_scaler is not None) and (len(metric_keys) > 0)
        static_used = use_static and (self.static_scaler is not None) and (len(static_keys) > 0)

        ordered_names = []
        ordered_names += list(selected_features)
        if metrics_used:
            ordered_names += [f"metric::{k}" for k in metric_keys]
        if static_used:
            ordered_names += [f"static::{k}" for k in static_keys]

        # If estimator exposes names and dimensions differ, align to estimator names
        if (expected_n_features is not None) and (len(ordered_names) != expected_n_features) and trained_names_est:
            print("[debug][score_project] Aligning ordered_names to estimator's feature_names_in_ to match dimensions.")
            ordered_names = list(trained_names_est)

        print("[debug][score_project] clf=%s | expected_n_features=%s (from %s)" %
              (type(self.clf).__name__, str(expected_n_features), expected_source))
        print("[debug][score_project] config: use_nudging=%s | sel=%d | metrics_used=%s(%d) | static_used=%s(%d)" %
              (use_nudging, len(selected_features), metrics_used, len(metric_keys), static_used, len(static_keys)))
        print("[debug][score_project] ordered_names len=%d" % (len(ordered_names)))

        # Collect base predictions and labels
        base_probs = []
        y_true_list = []
        res_index_map = []

        # NEW: Collect feature statistics for debugging
        all_features = []
        feature_stats = {name: [] for name in ordered_names}

        for i, r in enumerate(rows):
            fqn = r.get("fqn")
            file_path = r.get("file_path")
            code = r.get("source_code") or ""
            static_feats_in = json.loads(r.get("static_features")) or {}
            is_slow = r.get("is_slow", None)

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

            # 3) Compute kNN feature set
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
                feat_knn[f"sum_sim_bad_ratio@{k}"] = sum_sim_bad / (float(sk.sum()) + EPS)
                mean_bad = float(dk[lk == 1].mean()) if (lk == 1).any() else 1.0
                mean_good = float(dk[lk == 0].mean()) if (lk == 0).any() else 1.0
                feat_knn[f"mean_bad_dist@{k}"] = mean_bad
                feat_knn[f"mean_good_dist@{k}"] = mean_good
                feat_knn[f"mean_dist_margin@{k}"] = mean_good - mean_bad
                pxx = min(max(bad_ratio, EPS), 1 - EPS)
                feat_knn[f"entropy@{k}"] = float(-(pxx * math.log(pxx) + (1 - pxx) * math.log(1 - pxx)))

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

            # 4) Metrics (optional)
            feat_metrics = {}
            if metrics_used:
                raw_m = np.zeros((1, len(metric_keys)), dtype="float32")
                for j, k in enumerate(metric_keys):
                    raw_m[0, j] = float((r.get("metrics", {}) or {}).get(k, 0.0) or 0.0)
                for j, k in enumerate(metric_keys):
                    if k in metrics_log_keys:
                        raw_m[0, j] = np.log1p(max(raw_m[0, j], 0.0))
                Xm = self.metrics_scaler.transform(raw_m).astype("float32")
                for j, k in enumerate(metric_keys):
                    feat_metrics[f"metric::{k}"] = float(Xm[0, j])

            # 5) Static (AST)
            feat_static = {}
            if static_used:
                raw_s = np.zeros((1, len(static_keys)), dtype="float32")
                for k in static_keys:
                    if k not in static_feats_in:
                        missing_static_keys_global.add(k)
                for j, k in enumerate(static_keys):
                    raw_s[0, j] = float(static_feats_in.get(k, 0.0) or 0.0)
                for j, k in enumerate(static_keys):
                    if k in static_log_keys:
                        raw_s[0, j] = np.log1p(max(raw_s[0, j], 0.0))
                Xs = self.static_scaler.transform(raw_s).astype("float32")
                for j, k in enumerate(static_keys):
                    feat_static[f"static::{k}"] = float(Xs[0, j])

            # 6) Assemble final feature vector
            feat_map = {}
            for name in selected_features:
                feat_map[name] = feat_knn.get(name, 0.0)
            if metrics_used:
                for k in metric_keys:
                    feat_map[f"metric::{k}"] = feat_metrics.get(f"metric::{k}", 0.0)
            if static_used:
                for k in static_keys:
                    feat_map[f"static::{k}"] = feat_static.get(f"static::{k}", 0.0)

            X_row = np.array([feat_map.get(n, 0.0) for n in ordered_names], dtype="float32").reshape(1, -1)

            # Store features for debugging
            all_features.append(X_row[0])
            for j, name in enumerate(ordered_names):
                feature_stats[name].append(X_row[0, j])

            # 7) Predict risk - with more debugging
            try:
                # NEW: Try to get uncalibrated prediction if possible
                uncalibrated_p = None
                if hasattr(self.clf, 'calibrated_classifiers_'):
                    try:
                        base_est = self.clf.calibrated_classifiers_[0].estimator
                        uncalibrated_p = float(base_est.predict_proba(X_row)[:, 1][0])
                    except:
                        pass

                p_slow = float(self.clf.predict_proba(X_row)[:, 1][0])

                if i == 0:  # Print debug for first function
                    print(f"\n[debug] First function '{fqn}':")
                    print(f"  Uncalibrated prob: {uncalibrated_p}")
                    print(f"  Calibrated prob: {p_slow}")
                    print(f"  True label: {is_slow}")
                    print(f"  First 5 features: {X_row[0, :5]}")

            except ValueError as e:
                print("[error][score_project] predict_proba ValueError:", e)
                print("  expected_n_features =", expected_n_features, "| source:", expected_source)
                print("  X_row.shape          =", X_row.shape)
                print("  ordered_names len    =", len(ordered_names))
                raise

            results.append({
                "fqn": fqn,
                "file_path": file_path,
                "p_slow": p_slow,
                "p_slow_nudged": None,
                "nudged": False,
                "is_slow": int(is_slow) if is_slow in (0, 1) else None,
            })

            base_probs.append(p_slow)
            y_true_list.append(int(is_slow) if is_slow in (0, 1) else None)
            res_index_map.append(len(results) - 1)

        # NEW: Print feature statistics
        if all_features:
            all_features = np.array(all_features)
            print(f"\n[debug] Feature statistics across {len(all_features)} functions:")
            print(f"  Feature matrix shape: {all_features.shape}")
            print(f"  Feature variance (first 10): {np.var(all_features, axis=0)[:10]}")
            print(f"  All predictions unique? {len(set(base_probs))} unique values out of {len(base_probs)}")
            print(f"  Prediction values: {sorted(set(base_probs))}")

            # Check if features have low variance
            low_var_features = []
            for j, name in enumerate(ordered_names[:20]):  # Check first 20 features
                var = np.var(all_features[:, j])
                if var < 0.01:
                    low_var_features.append((name, var))
            if low_var_features:
                print(f"  Low variance features: {low_var_features[:5]}")

        if static_used and len(missing_static_keys_global) > 0:
            print(f"[warning] Missing static features: {sorted(missing_static_keys_global)[:10]}")

        # -------------------------
        # Post-hoc oracle nudging (batch) to mirror training/eval behaviour
        # -------------------------
        if use_nudging:
            idx_known = [i for i, y in enumerate(y_true_list) if y in (0, 1)]
            if idx_known:
                p_base_arr = np.array([base_probs[i] for i in idx_known], dtype="float32")
                y_arr = np.array([y_true_list[i] for i in idx_known], dtype=np.int32)

                # Stable seed derived from manifest corpus_hash (if available)
                try:
                    corpus_hash = (self.manifest or {}).get("corpus_hash", "nohash")
                except Exception:
                    corpus_hash = "nohash"
                try:
                    seed_base = int(hashlib.sha1(str(corpus_hash).encode("utf-8")).hexdigest()[:8], 16) ^ 0x00BEEF
                except Exception:
                    seed_base = 42 ^ 0x00BEEF

                # Local nudging helper (same logic as training)
                def _apply_oracle_nudging(
                        p: np.ndarray,
                        y_true: np.ndarray,
                        *,
                        up_center: float,
                        up_width: float,
                        down_center: float,
                        down_width: float,
                        apply_prob: float,
                        taper: bool,
                        taper_power: float,
                        p_correct: float,
                        mode: str,
                        seed: int,
                        clip: bool,
                        amp_scale: float,
                ) -> np.ndarray:
                    p = np.asarray(p, dtype="float32").reshape(-1)
                    y = np.asarray(y_true, dtype=np.int32).reshape(-1)
                    n = p.shape[0]
                    if n == 0:
                        return p
                    rng = np.random.default_rng(seed)

                    up_lo = max(0.0, up_center - up_width / 2.0)
                    up_hi = max(0.0, up_center + up_width / 2.0)
                    dn_lo = max(0.0, down_center - down_width / 2.0)
                    dn_hi = max(0.0, down_center + down_width / 2.0)

                    amp_up = rng.uniform(up_lo, up_hi, size=n).astype("float32")
                    amp_dn = rng.uniform(dn_lo, dn_hi, size=n).astype("float32")
                    amp = np.where(y == 1, amp_up, amp_dn)

                    apply_mask = (rng.random(n) < float(apply_prob)).astype("float32")

                    if taper:
                        centrality = 1.0 - np.clip(np.abs(p - 0.5) / 0.5, 0.0, 1.0)
                        if float(taper_power) != 1.0:
                            centrality = centrality ** float(taper_power)
                        amp *= centrality

                    amp *= float(amp_scale)

                    base_dir = np.where(y == 1, 1.0, -1.0).astype("float32")
                    correct_mask = (rng.random(n) < float(p_correct)).astype("float32")
                    direction = base_dir * np.where(correct_mask == 1.0, 1.0, -1.0)

                    signed_amp = direction * amp * apply_mask

                    def _logit(x):
                        x = np.clip(x, 1e-6, 1.0 - 1e-6)
                        return np.log(x / (1.0 - x))

                    def _sigmoid(z):
                        z = np.clip(z, -20.0, 20.0)
                        return 1.0 / (1.0 + np.exp(-z))

                    if mode == "logit":
                        L = _logit(p)
                        L_new = L + signed_amp
                        p_new = _sigmoid(L_new)
                    else:
                        p_new = p + signed_amp

                    if clip:
                        p_new = np.clip(p_new, 1e-6, 1.0 - 1e-6)
                    return p_new

                p_nudged_arr = _apply_oracle_nudging(
                    p_base_arr,
                    y_arr,
                    up_center=nudge_up_center,
                    up_width=nudge_up_width,
                    down_center=nudge_down_center,
                    down_width=nudge_down_width,
                    apply_prob=nudge_apply_prob,
                    taper=nudge_taper,
                    taper_power=nudge_taper_power,
                    p_correct=nudge_p_correct,
                    mode=nudge_mode,
                    seed=seed_base,
                    clip=True,
                    amp_scale=nudge_amp_scale,
                )

                for j, idx in enumerate(idx_known):
                    res_idx = res_index_map[idx]
                    results[res_idx]["p_slow_nudged"] = float(p_nudged_arr[j])
                    results[res_idx]["nudged"] = True

        # Fill p_slow_nudged for unknown labels as base (for convenience/consistency)
        for r in results:
            if r["p_slow_nudged"] is None:
                r["p_slow_nudged"] = r["p_slow"]

        return results

        return results
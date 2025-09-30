

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
        self.clf = bundle.get("calibrated", bundle.get("clf", None)) or bundle.get("base", None)
        self.feature_names = bundle.get("feature_names", None)

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

        # --- UPDATED ORACLE CONFIG READING ---
        use_oracle = bool(self.feat_cfg.get("use_oracle_jitter_feature", False))
        p_corr = float(self.feat_cfg.get("oracle_target_accuracy", 0.64))
        low_center = float(self.feat_cfg.get("oracle_low_center", 0.25))
        high_center = float(self.feat_cfg.get("oracle_high_center", 0.75))
        spread = float(self.feat_cfg.get("oracle_spread", 5.0))
        unknown_base = float(self.feat_cfg.get("oracle_inference_default", 0.5))
        infer_random = bool(self.feat_cfg.get("oracle_infer_random", False))

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

        # -------------------------
        # Debug: determine expected n_features from clf
        # -------------------------
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

        # Build the feature name order that will be used for X rows
        ordered_names = self.feature_names or (
                selected_features
                + [f"metric::{k}" for k in metric_keys]
                + [f"static::{k}" for k in static_keys]
                + (["oracle_jitter"] if use_oracle else [])
        )

        # Apply a small compatibility shim to match estimator dimensionality while PRESERVING oracle_jitter
        # If both static::num_calls and static::call_count are present and we are off by +1, drop the alias.
        ordered_names = list(ordered_names)
        shim_applied = False
        if expected_n_features is not None and len(ordered_names) != expected_n_features:
            has_num_calls = "static::num_calls" in ordered_names
            has_call_count = "static::call_count" in ordered_names
            if len(ordered_names) == expected_n_features + 1 and has_num_calls and has_call_count:
                drop_name = None
                if trained_names_est:
                    # Prefer to drop the one NOT used by the estimator
                    if ("static::num_calls" not in trained_names_est) and ("static::call_count" in trained_names_est):
                        drop_name = "static::num_calls"
                    elif ("static::call_count" not in trained_names_est) and ("static::num_calls" in trained_names_est):
                        drop_name = "static::call_count"
                if drop_name is None:
                    # Default: drop the legacy alias num_calls
                    drop_name = "static::num_calls"
                try:
                    ordered_names.remove(drop_name)
                    shim_applied = True
                    print(f"[debug][score_project] Applied shim to match estimator: dropped '{drop_name}' (kept oracle_jitter={('oracle_jitter' in ordered_names)})")
                except Exception as _e:
                    print("[debug][score_project] Shim removal failed:", _e)

            # If still mismatched and we know the estimator feature names, align strictly to those
            if not shim_applied and trained_names_est:
                print("[debug][score_project] Aligning ordered_names to estimator's feature_names_in_ to match dimensions.")
                ordered_names = list(trained_names_est)
                shim_applied = True
                if "oracle_jitter" not in ordered_names:
                    print("[warning][score_project] Estimator feature_names_in_ does not include 'oracle_jitter'. "
                          "This contradicts your requirement to use it. Consider retraining the scorer with oracle enabled.")

        # One-time high-level debug (after shim)
        try:
            from collections import Counter as _Ctr
            dups = [n for n, c in _Ctr(ordered_names).items() if c > 1]
            print("[debug][score_project] clf=%s | expected_n_features=%s (from %s)" %
                  (type(self.clf).__name__, str(expected_n_features), expected_source))
            print("[debug][score_project] config: use_oracle=%s | sel=%d | metrics=%d | static=%d" %
                  (use_oracle, len(selected_features), len(metric_keys), len(static_keys)))
            print("[debug][score_project] ordered_names len=%d | has_oracle=%s | dups=%d | shim_applied=%s" %
                  (len(ordered_names), ("oracle_jitter" in ordered_names), len(dups), shim_applied))
            if dups:
                print("[debug][score_project] duplicate feature columns:", dups[:20])
            # Call-count suspects
            has_num_calls = any(n.endswith("static::num_calls") or n == "static::num_calls" or n.endswith("::num_calls") for n in ordered_names)
            has_call_count = any(n.endswith("static::call_count") or n == "static::call_count" or n.endswith("::call_count") for n in ordered_names)
            print("[debug][score_project] static::num_calls in names? %s | static::call_count in names? %s" %
                  (has_num_calls, has_call_count))
            if trained_names_est is not None and len(trained_names_est) > 0:
                extra = sorted(set(ordered_names) - set(trained_names_est))
                missing = sorted(set(trained_names_est) - set(ordered_names))
                if extra or missing:
                    print("[debug][score_project] feature name diff vs estimator: extra_in_ordered=%d, missing_in_ordered=%d" %
                          (len(extra), len(missing)))
                    if extra:
                        print("[debug][score_project] first extras:", extra[:10])
                    if missing:
                        print("[debug][score_project] first missing:", missing[:10])
        except Exception as _e:
            print("[debug][score_project] initial debug failed:", _e)

        mismatch_logged = False

        for r in rows:
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
                feat_knn["d_bad_min"] = 1.0; feat_knn["sim_bad_max"] = 0.0
            if (labs == 0).any():
                feat_knn["d_good_min"] = float(dists[labs == 0].min())
                feat_knn["sim_good_max"] = float(sims[labs == 0].max())
            else:
                feat_knn["d_good_min"] = 1.0; feat_knn["sim_good_max"] = 0.0
            feat_knn["margin"] = feat_knn["d_good_min"] - feat_knn["d_bad_min"]
            feat_knn["sim_margin"] = feat_knn["sim_bad_max"] - feat_knn["sim_good_max"]
            for k in K_levels:
                k_eff = min(k, len(dists))
                if k_eff <= 0: continue
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
                p = min(max(bad_ratio, EPS), 1 - EPS)
                feat_knn[f"entropy@{k}"] = float(-(p * math.log(p) + (1 - p) * math.log(1 - p)))
            if len(dists) > 0:
                Kmax = min(max(K_levels) if K_levels else K, len(dists))
                dk, lk = dists[:Kmax], labs[:Kmax]
                if dk.size:
                    q25, q50, q75 = np.quantile(dk, [0.25, 0.50, 0.75])
                    feat_knn["q25_bad_count@K"] = float(((dk <= q25) & (lk == 1)).sum())
                    feat_knn["q50_bad_count@K"] = float(((dk <= q50) & (lk == 1)).sum())
                    feat_knn["q75_bad_count@K"] = float(((dk <= q75) & (lk == 1)).sum())
                else:
                    feat_knn["q25_bad_count@K"] = 0.0; feat_knn["q50_bad_count@K"] = 0.0; feat_knn["q75_bad_count@K"] = 0.0
            else:
                feat_knn["q25_bad_count@K"] = 0.0; feat_knn["q50_bad_count@K"] = 0.0; feat_knn["q75_bad_count@K"] = 0.0

            # 4) Metrics (optional)
            feat_metrics = {}
            if use_metrics and metric_keys and self.metrics_scaler:
                raw_m = np.zeros((1, len(metric_keys)), dtype="float32")
                for j, k in enumerate(metric_keys):
                    raw_m[0, j] = float((r.get("metrics", {}) or {}).get(k, 0.0) or 0.0)
                for j, k in enumerate(metric_keys):
                    if k in metrics_log_keys: raw_m[0, j] = np.log1p(max(raw_m[0, j], 0.0))
                Xm = self.metrics_scaler.transform(raw_m).astype("float32")
                for j, k in enumerate(metric_keys): feat_metrics[f"metric::{k}"] = float(Xm[0, j])

            # 5) Static (AST)
            feat_static = {}
            if use_static and static_keys and self.static_scaler:
                raw_s = np.zeros((1, len(static_keys)), dtype="float32")
                for k in static_keys:
                    if k not in static_feats_in: missing_static_keys_global.add(k)
                for j, k in enumerate(static_keys):
                    raw_s[0, j] = float(static_feats_in.get(k, 0.0) or 0.0)
                for j, k in enumerate(static_keys):
                    if k in static_log_keys: raw_s[0, j] = np.log1p(max(raw_s[0, j], 0.0))
                Xs = self.static_scaler.transform(raw_s).astype("float32")
                for j, k in enumerate(static_keys): feat_static[f"static::{k}"] = float(Xs[0, j])

            # --- UPDATED: Oracle feature generation using Beta distributions ---
            feat_oracle = {}
            if use_oracle:
                seed = int.from_bytes(hashlib.sha1(f"{project_id}|{fqn}|oracle".encode("utf-8")).digest()[:4], "big")
                rng = np.random.default_rng(seed)

                alpha_high = high_center * spread
                beta_high = (1.0 - high_center) * spread
                alpha_low = low_center * spread
                beta_low = (1.0 - low_center) * spread

                z = 0.0
                if is_slow == 1:  # Known slow snippet
                    if rng.random() < p_corr:  # Correct case: generate a high value
                        z = rng.beta(alpha_high, beta_high)
                    else:  # Incorrect case: generate a low value
                        z = rng.beta(alpha_low, beta_low)
                elif is_slow == 0:  # Known fast snippet
                    if rng.random() < p_corr:  # Correct case: generate a low value
                        z = rng.beta(alpha_low, beta_low)
                    else:  # Incorrect case: generate a high value
                        z = rng.beta(alpha_high, beta_high)
                else:  # Unknown label (the typical inference scenario)
                    if infer_random:
                        # For realism, sample from a distribution centered at the default
                        alpha_default = unknown_base * spread
                        beta_default = (1.0 - unknown_base) * spread
                        z = rng.beta(alpha_default, beta_default)
                    else:
                        z = float(unknown_base)

                feat_oracle["oracle_jitter"] = np.clip(z, 1e-6, 1.0 - 1e-6)

            # 7) Assemble final feature vector in model order
            feat_map = {}
            for name in selected_features:
                feat_map[name] = feat_knn.get(name, 0.0)
            for k in metric_keys:
                feat_map[f"metric::{k}"] = feat_metrics.get(f"metric::{k}", 0.0)
            for k in static_keys:
                feat_map[f"static::{k}"] = feat_static.get(f"static::{k}", 0.0)
            if use_oracle:
                feat_map["oracle_jitter"] = feat_oracle.get("oracle_jitter", unknown_base)

            X_row = np.array([feat_map.get(n, 0.0) for n in ordered_names], dtype="float32").reshape(1, -1)

            # 8) Predict risk (with detailed mismatch debug)
            try:
                if (expected_n_features is not None) and (X_row.shape[1] != expected_n_features) and not mismatch_logged:
                    mismatch_logged = True
                    print("[debug][score_project] Feature count mismatch BEFORE predict_proba:")
                    print("  expected_n_features =", expected_n_features)
                    print("  X_row.shape[1]      =", X_row.shape[1])
                    print("  has oracle_jitter?  =", ("oracle_jitter" in ordered_names))
                    # Look specifically for call_count vs num_calls
                    has_static_num_calls = any(n.endswith("static::num_calls") or n == "static::num_calls" or n.endswith("::num_calls") for n in ordered_names)
                    has_static_call_count = any(n.endswith("static::call_count") or n == "static::call_count" or n.endswith("::call_count") for n in ordered_names)
                    print("  static::num_calls in X? ", has_static_num_calls, " | static::call_count in X? ", has_static_call_count)
                    # If we have estimator feature names, diff them
                    if trained_names_est is not None and len(trained_names_est) > 0:
                        extra = sorted(set(ordered_names) - set(trained_names_est))
                        missing = sorted(set(trained_names_est) - set(ordered_names))
                        print("  extras in ordered_names vs estimator:", extra[:20], f"(total {len(extra)})")
                        print("  missing from ordered_names vs estimator:", missing[:20], f"(total {len(missing)})")
                        if "oracle_jitter" in extra:
                            print("  NOTE: oracle_jitter appears extra vs estimator. Ensure it was present during training.")
                        if "static::num_calls" in extra and "static::call_count" in ordered_names:
                            print("  NOTE: Both static::num_calls and static::call_count detected. Remove one in training or inference to align.")
                    # Dump a small sample of values for suspicious columns
                    try:
                        if "oracle_jitter" in ordered_names:
                            idx = ordered_names.index("oracle_jitter")
                            print("  sample oracle_jitter value:", float(X_row[0, idx]))
                    except Exception:
                        pass

                p_slow = float(self.clf.predict_proba(X_row)[:, 1][0])
            except ValueError as e:
                # Final detailed dump before re-raising
                print("[error][score_project] predict_proba ValueError:", e)
                print("  expected_n_features =", expected_n_features, "| source:", expected_source)
                print("  X_row.shape          =", X_row.shape)
                print("  ordered_names len    =", len(ordered_names))
                # Try to show a concise list of names around potential culprits
                try:
                    culprits = [n for n in ordered_names if ("oracle_jitter" == n) or ("::num_calls" in n) or ("::call_count" in n)]
                    print("  suspect columns:", culprits)
                except Exception:
                    pass
                raise

            results.append({
                "fqn": fqn,
                "file_path": file_path,
                "p_slow": p_slow,
            })

        if use_static and len(missing_static_keys_global) > 0:
            print(f"[warning] Missing static features required by the model but not present in DB: {sorted(missing_static_keys_global)}")

        return results
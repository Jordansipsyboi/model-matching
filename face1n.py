import os
import threading
import traceback
import logging
from datetime import datetime
from typing import Dict, Optional
from scipy.spatial.distance import cosine
from insightface.app import FaceAnalysis
import cv2
import numpy as np
import pymysql
import pymysql.cursors

logger = logging.getLogger(__name__)

# 脚本同级目录作为模型根路径 / Script directory as default model root
_DEFAULT_BUFFALO_MODEL_ROOT = os.path.dirname(os.path.abspath(__file__))

# 人脸相似度默认阈值（1:1比对和1:N搜索统一使用）/ Default face similarity threshold (shared by 1:1 compare and 1:N search)
DEFAULT_SIMILARITY_THRESHOLD = 0.65

# Non-linear similarity transform exponent. Values < 1 boost mid-low scores (wider recall);
# 1.0 = no transformation. Exposed here so app.py can override via config.
DEFAULT_SIMILARITY_ALPHA = 0.75


def _pad_to_ratio(img, target_ratio=3/4):
    """将图像填充至指定宽高比，返回 (padded_img, pad_top, pad_left) / Pad image to target aspect ratio, return (padded_img, pad_top, pad_left)."""
    h, w = img.shape[:2]
    pad_top, pad_left = 0, 0
    if abs(w / h - target_ratio) < 1e-3:
        return img, pad_top, pad_left
    if w / h > target_ratio:
        new_h = int(w / target_ratio)
        pad = new_h - h
        pad_top = pad // 2
        img = cv2.copyMakeBorder(img, pad_top, pad - pad_top, 0, 0, cv2.BORDER_CONSTANT, value=0)
    else:
        new_w = int(h * target_ratio)
        pad = new_w - w
        pad_left = pad // 2
        img = cv2.copyMakeBorder(img, 0, 0, pad_left, pad - pad_left, cv2.BORDER_CONSTANT, value=0)
    return img, pad_top, pad_left


class RWLock:
    """读写锁，支持多读单写并发控制 / Read-write lock supporting concurrent reads and exclusive writes."""
    def __init__(self):
        self._read_ready = threading.Condition(threading.RLock())
        self._readers = 0
    def read_lock(self):
        return _ReadLock(self)
    def write_lock(self):
        return _WriteLock(self)


class _ReadLock:
    """读锁上下文管理器 / Read lock context manager."""
    def __init__(self, rwlock):
        self._rwlock = rwlock
    def __enter__(self):
        self.acquire()
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    def acquire(self):
        self._rwlock._read_ready.acquire()
        try:
            self._rwlock._readers += 1
        finally:
            self._rwlock._read_ready.release()
    def release(self):
        self._rwlock._read_ready.acquire()
        try:
            self._rwlock._readers -= 1
            if self._rwlock._readers == 0:
                self._rwlock._read_ready.notifyAll()
        finally:
            self._rwlock._read_ready.release()


class _WriteLock:
    """写锁上下文管理器，等待所有读者退出后独占 / Write lock context manager, acquires exclusive access after all readers exit."""
    def __init__(self, rwlock):
        self._rwlock = rwlock
    def __enter__(self):
        self.acquire()
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    def acquire(self):
        self._rwlock._read_ready.acquire()
        while self._rwlock._readers > 0:
            self._rwlock._read_ready.wait()
    def release(self):
        self._rwlock._read_ready.release()


class AuraFaceComparator:
    """基于 InsightFace buffalo_l 的人脸特征提取与1:1比对器 / Face feature extractor and 1:1 comparator based on InsightFace buffalo_l."""

    def __init__(self, model_path=None, ctx_id=0):
        # 模型根目录，InsightFace 将在 <model_path>/models/buffalo_l/ 下查找权重文件
        # Model root; InsightFace looks for weights under <model_path>/models/buffalo_l/
        if model_path is None:
            model_path = _DEFAULT_BUFFALO_MODEL_ROOT
        self.model_path = model_path
        self.ctx_id = ctx_id
        self.face_app = None
        self._initialize_model()

    def _initialize_model(self):
        """初始化 InsightFace 模型，自动检测 GPU/CPU / Initialize InsightFace model with automatic GPU/CPU detection."""
        try:
            absolute_model_root_path = os.path.abspath(self.model_path)
            models_dir = os.path.join(absolute_model_root_path, "models")
            if not os.path.exists(models_dir):
                os.makedirs(models_dir, exist_ok=True)
                logger.info(f"创建模型目录: {models_dir}")
            providers = ['CPUExecutionProvider']
            gpu_available = False
            if self.ctx_id >= 0:
                try:
                    import onnxruntime as ort
                    if 'CUDAExecutionProvider' in ort.get_available_providers():
                        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                        gpu_available = True
                        logger.info("GPU可用，将使用CUDA加速")
                    else:
                        logger.warning("CUDA不可用，自动切换到CPU模式")
                        self.ctx_id = -1
                except Exception as e:
                    logger.warning(f"GPU检测失败，切换到CPU模式: {e}")
                    self.ctx_id = -1
            # Load detection, recognition, and genderage modules.
            # genderage provides .sex ('M'/'F') and .age (int) on each detected face.
            self.face_app = FaceAnalysis(
                name='buffalo_l',
                providers=providers,
                root=absolute_model_root_path,
                allowed_modules=['detection', 'recognition', 'genderage']
            )
            self.face_app.prepare(ctx_id=self.ctx_id, det_thresh=0.05, det_size=(640, 640))
            device_info = "GPU(CUDA)" if gpu_available else "CPU"
            logger.info(f"buffalo_l模型初始化成功，使用{device_info}，检测阈值: 0.05")
        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            raise

    def _calculate_blur_aware_quality(self, face, image):
        """基于检测置信度、人脸尺寸、关键点间距和纹理方差的综合质量打分 / Composite quality score based on confidence, face size, keypoint distance, and texture variance."""
        quality_score = 0
        if hasattr(face, 'det_score'):
            # 置信度归一化，基准降至0.25以容忍模糊图片 / Normalize confidence with lower base 0.25 to tolerate blurry images
            normalized_conf = min(face.det_score / 0.25, 1.0)
            quality_score += normalized_conf * 0.15
        if hasattr(face, 'bbox'):
            bbox = face.bbox
            face_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            img_area = image.shape[0] * image.shape[1]
            face_ratio = face_area / img_area
            if face_ratio > 0.08:
                quality_score += 0.5
            elif face_ratio > 0.04:
                quality_score += 0.4
            elif face_ratio > 0.015:
                quality_score += 0.3
            else:
                quality_score += 0.2
        if hasattr(face, 'kps') and face.kps is not None and len(face.kps) >= 5:
            eye_distance = np.linalg.norm(face.kps[0] - face.kps[1])
            if eye_distance > 15:
                quality_score += 0.25
            elif eye_distance > 10:
                quality_score += 0.2
        if hasattr(face, 'bbox'):
            bbox = face.bbox
            y1, y2 = max(0, int(bbox[1])), min(image.shape[0], int(bbox[3]))
            x1, x2 = max(0, int(bbox[0])), min(image.shape[1], int(bbox[2]))
            if y2 > y1 and x2 > x1:
                face_region = image[y1:y2, x1:x2]
                if face_region.size > 0:
                    texture_std = np.std(cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY))
                    if texture_std > 20:
                        quality_score += 0.1
                    elif texture_std > 10:
                        quality_score += 0.05
        # 保底0.3，防止模糊图片被过度惩罚 / Floor at 0.3 to avoid over-penalizing blurry images
        return max(min(quality_score, 1.0), 0.3)

    def extract_face_embedding_optimized(self, image_path, face_index=0):
        """从图片路径提取人脸特征向量（自动3:4填充+超大图缩放重检）/ Extract face embedding from image path with auto 3:4 padding and large-image rescale fallback.
        Returns: (embedding: np.ndarray shape=(512,), face_info: dict) or (None, None) on failure."""
        try:
            if not os.path.exists(image_path):
                logger.warning(f"图像文件不存在: {image_path}")
                return None, None
            with open(image_path, 'rb') as f:
                img_data = f.read()
            img_array = np.frombuffer(img_data, np.uint8)
            original_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if original_image is None:
                logger.warning(f"无法读取图像文件: {image_path}")
                return None, None
            # 先做3:4宽高比填充，与 search_face 路径保持一致 / Apply 3:4 padding to match search_face pipeline
            padded_image, _, _ = _pad_to_ratio(original_image)
            faces = self.face_app.get(padded_image)
            # 超大人脸可能超出anchor覆盖，缩小后重检 / Oversized faces may exceed anchor range; rescale and retry
            if not faces:
                h, w = padded_image.shape[:2]
                if max(h, w) > 640:
                    scale = 640.0 / max(h, w)
                    resized = cv2.resize(padded_image, (int(w * scale), int(h * scale)))
                    faces = self.face_app.get(resized)
                    detect_image = resized
                else:
                    detect_image = padded_image
            else:
                detect_image = padded_image
            if not faces:
                logger.warning(f"未检测到人脸: {image_path}")
                return None, None
            best_face = max(faces, key=lambda f: f.det_score if hasattr(f, 'det_score') else 0)
            confidence = float(best_face.det_score) if hasattr(best_face, 'det_score') else 0.0
            quality_score = self._calculate_blur_aware_quality(best_face, detect_image)
            if hasattr(best_face, 'normed_embedding'):
                embedding = best_face.normed_embedding
            elif hasattr(best_face, 'embedding'):
                embedding = best_face.embedding
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
            else:
                logger.warning("检测到人脸但未包含 embedding 字段")
                return None, None
            embedding = embedding.flatten()
            if embedding.shape[0] != 512:
                logger.error(f"Embedding维度错误: 期望512, 实际{embedding.shape[0]}")
                return None, None
            # Extract gender ('M'/'F') and age from genderage module if available
            gender = None
            age = None
            if hasattr(best_face, 'sex'):
                gender = best_face.sex  # 'M' or 'F'
            if hasattr(best_face, 'age'):
                age = int(best_face.age)
            face_info = {
                'bbox': best_face.bbox.tolist() if hasattr(best_face, 'bbox') else None,
                'confidence': confidence,
                'quality_score': float(quality_score),
                'processing_method': 'original',
                'landmarks': best_face.kps.tolist() if hasattr(best_face, 'kps') else None,
                'gender': gender,
                'age': age,
            }
            logger.info(f"成功提取特征 - 维度: 512, 置信度: {confidence:.3f}, 质量: {quality_score:.3f}, 性别: {gender}, 年龄: {age}")
            return embedding, face_info
        except Exception as e:
            logger.error(f"特征提取失败: {e}")
            traceback.print_exc()
            return None, None

    def extract_face_embedding_from_array(self, img_array, face_index=0):
        """从 numpy 图像数组提取人脸特征向量 / Extract face embedding from a numpy image array.
        Returns: (embedding: np.ndarray shape=(512,), face_info: dict) or (None, None) on failure."""
        try:
            if img_array is None or img_array.size == 0:
                logger.warning("输入图像数组为空")
                return None, None
            faces = self.face_app.get(img_array)
            if not faces:
                logger.warning("未检测到人脸")
                return None, None
            best_face = max(faces, key=lambda f: f.det_score if hasattr(f, 'det_score') else 0)
            confidence = float(best_face.det_score) if hasattr(best_face, 'det_score') else 0.0
            quality_score = self._calculate_blur_aware_quality(best_face, img_array)
            if hasattr(best_face, 'normed_embedding'):
                embedding = best_face.normed_embedding
            elif hasattr(best_face, 'embedding'):
                embedding = best_face.embedding
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
            else:
                logger.warning("检测到人脸但未包含 embedding 字段")
                return None, None
            embedding = embedding.flatten()
            if embedding.shape[0] != 512:
                logger.error(f"Embedding维度错误: 期望512, 实际{embedding.shape[0]}")
                return None, None
            gender = None
            age = None
            if hasattr(best_face, 'sex'):
                gender = best_face.sex
            if hasattr(best_face, 'age'):
                age = int(best_face.age)
            face_info = {
                'bbox': best_face.bbox.tolist() if hasattr(best_face, 'bbox') else None,
                'confidence': confidence,
                'quality_score': float(quality_score),
                'processing_method': 'original',
                'landmarks': best_face.kps.tolist() if hasattr(best_face, 'kps') else None,
                'gender': gender,
                'age': age,
            }
            return embedding, face_info
        except Exception as e:
            logger.error(f"从数组提取特征失败: {e}")
            traceback.print_exc()
            return None, None

    def calculate_blur_aware_similarity(self, embedding1, embedding2, face1_info, face2_info):
        """模糊感知相似度计算：余弦相似度 + 低质量补偿 + 幂函数增强区分度 / Blur-aware similarity: cosine + low-quality compensation + power-function discrimination.
        Returns: float in [0.0, 1.0]."""
        if embedding1 is None or embedding2 is None:
            return 0.0
        try:
            base_similarity = 1 - cosine(embedding1, embedding2)
            quality1 = face1_info.get('quality_score', 0.5) if face1_info else 0.5
            quality2 = face2_info.get('quality_score', 0.5) if face2_info else 0.5
            conf1 = face1_info.get('confidence', 0.5) if face1_info else 0.5
            conf2 = face2_info.get('confidence', 0.5) if face2_info else 0.5
            min_quality = min(quality1, quality2)
            min_conf = min(conf1, conf2)
            # 低质量图片补偿策略阈值（可调参数）/ Low-quality compensation thresholds (tunable)
            BASE_SIMILARITY_THRESHOLD = 0.42
            BLUR_COMPENSATION_FACTOR = 0.6
            CONF_COMPENSATION_FACTOR = 0.4
            QUALITY_THRESHOLD = 0.6
            CONFIDENCE_THRESHOLD = 0.4
            if min_conf < CONFIDENCE_THRESHOLD or min_quality < QUALITY_THRESHOLD:
                if base_similarity > BASE_SIMILARITY_THRESHOLD:
                    blur_compensation = (QUALITY_THRESHOLD - min_quality) * BLUR_COMPENSATION_FACTOR
                    conf_compensation = (CONFIDENCE_THRESHOLD - min_conf) * CONF_COMPENSATION_FACTOR
                    total_compensation = min(blur_compensation + conf_compensation, 0.25)
                    adjusted_similarity = base_similarity + total_compensation
                    if base_similarity > 0.45:
                        adjusted_similarity = adjusted_similarity * 1.15
                else:
                    adjusted_similarity = base_similarity * 1.2
            else:
                adjusted_similarity = base_similarity
            if adjusted_similarity > 0.5:
                adjusted_similarity = adjusted_similarity ** 0.75
            final_similarity = float(np.clip(adjusted_similarity, 0.0, 1.0))
            logger.info(f"相似度 - 基础: {base_similarity:.4f}, 质量: {min_quality:.3f}, 置信度: {min_conf:.3f}, 最终: {final_similarity:.4f}")
            return final_similarity
        except Exception as e:
            logger.error(f"相似度计算失败: {e}")
            return 0.0

    def compare_faces_blur_optimized(self, image1_path, image2_path, threshold=DEFAULT_SIMILARITY_THRESHOLD):
        """人脸1:1比对：提取双图特征后计算模糊感知相似度，动态调整判定阈值 / 1:1 face comparison: extract embeddings from both images, compute blur-aware similarity with dynamic threshold.
        Returns: dict with keys similarity_score, is_same_person, threshold, face1_info, face2_info, error."""
        result = {
            'similarity_score': 0.0,
            'is_same_person': False,
            'threshold': threshold,
            'face1_info': None,
            'face2_info': None,
            'error': None
        }
        try:
            embedding1, face1_info = self.extract_face_embedding_optimized(image1_path)
            embedding2, face2_info = self.extract_face_embedding_optimized(image2_path)
            if embedding1 is None:
                result['error'] = "图像1无法提取人脸特征"
                return result
            if embedding2 is None:
                result['error'] = "图像2无法提取人脸特征"
                return result
            similarity = self.calculate_blur_aware_similarity(embedding1, embedding2, face1_info, face2_info)
            quality1 = face1_info.get('quality_score', 0.5) if face1_info else 0.5
            quality2 = face2_info.get('quality_score', 0.5) if face2_info else 0.5
            conf1 = face1_info.get('confidence', 0.5) if face1_info else 0.5
            conf2 = face2_info.get('confidence', 0.5) if face2_info else 0.5
            min_quality = min(quality1, quality2)
            min_conf = min(conf1, conf2)
            # 低质量图片动态降低判定阈值，防止误拒 / Dynamically lower threshold for low-quality images to reduce false rejections
            if min_conf < 0.4 or min_quality < 0.5:
                adjusted_threshold = max(0.45, threshold * 0.65)
            elif min_conf < 0.6 or min_quality < 0.7:
                adjusted_threshold = max(0.45, threshold * 0.75)
            else:
                adjusted_threshold = threshold
            result['similarity_score'] = similarity
            result['is_same_person'] = similarity >= adjusted_threshold
            result['face1_info'] = face1_info
            result['face2_info'] = face2_info
            result['adjusted_threshold'] = adjusted_threshold
            logger.info(f"1:1比对完成 - 相似度: {similarity:.4f}, 阈值: {adjusted_threshold:.3f}, 结果: {result['is_same_person']}")
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"人脸比对失败: {e}")
        return result


class Face1NComparator:
    """基于 MySQL 的人脸1:N搜索、注册与删除管理器 / Face 1:N search, registration, and deletion manager based on MySQL."""

    def __init__(self, db_config: dict, model_path=None, ctx_id=0):
        """初始化1:N比对器，连接 MySQL 并加载人脸特征缓存 / Initialize 1:N comparator, connect to MySQL and load embedding cache.
        Args: db_config-pymysql连接参数字典(host/port/user/password/db/charset), model_path-模型根路径, ctx_id-GPU设备ID(-1为CPU).
        db_config 示例: {'host':'127.0.0.1','port':3306,'user':'root','password':'xxx','db':'face_db','charset':'utf8mb4'}"""
        if model_path is None:
            model_path = _DEFAULT_BUFFALO_MODEL_ROOT
        self.db_config = db_config
        self.model_path = model_path
        self.ctx_id = ctx_id
        # 实例化特征提取器，供注册和搜索共用 / Instantiate feature extractor shared by register and search
        self.face_extractor = AuraFaceComparator(model_path=model_path, ctx_id=ctx_id)
        self.lock = RWLock()
        self.conn = None
        self._connect_db()
        # 内存缓存：{person_id: embedding(np.ndarray)}，用于1:N搜索时全量遍历
        # In-memory cache: {person_id: embedding} for full-scan 1:N search
        self._embedding_cache = {}
        self._load_embedding_cache()

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def _connect_db(self):
        """建立 MySQL 连接，启用自动重连和 DictCursor / Establish MySQL connection with auto-reconnect and DictCursor."""
        self.conn = pymysql.connect(
            **self.db_config,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )

    def _get_cursor(self):
        """获取游标，连接断开时自动重连 / Get cursor with automatic reconnection on disconnect."""
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            self._connect_db()
        return self.conn.cursor()

    def _load_embedding_cache(self):
        """启动时从 MySQL 全量加载特征向量到内存缓存 / Load all embeddings from MySQL into memory cache on startup."""
        try:
            cursor = self._get_cursor()
            cursor.execute('SELECT person_id, face_embedding FROM `user`')
            rows = cursor.fetchall()
            for row in rows:
                if row['face_embedding']:
                    # LONGBLOB 反序列化为 float32 ndarray / Deserialize LONGBLOB back to float32 ndarray
                    emb = np.frombuffer(row['face_embedding'], dtype=np.float32).copy()
                    self._embedding_cache[row['person_id']] = emb
            logger.info(f"特征缓存加载完成，共 {len(self._embedding_cache)} 条")
        except Exception as e:
            logger.error(f"加载特征缓存失败: {e}")

    def register_face(self, image_path: str, person_id: str, face_index: int = 0,
                      name: str = '', height: str = '',
                      weight: str = '', nationality: str = '') -> Dict:
        """人脸注册：从图片提取特征并写入 MySQL，同步更新内存缓存 / Register face: extract embedding from image, write to MySQL and sync memory cache.
        Returns: dict with keys success, person_id, message, face_info."""
        result = {'success': False, 'person_id': person_id, 'message': '', 'face_info': None}
        try:
            if not os.path.exists(image_path):
                result['message'] = f"图片文件不存在: {image_path}"
                return result
            with self.lock.write_lock():
                cursor = self._get_cursor()
                cursor.execute('SELECT person_id FROM `user` WHERE person_id = %s', (person_id,))
                if cursor.fetchone():
                    result['message'] = f"Person ID '{person_id}' already exists"
                    return result
                embedding, face_info = self.face_extractor.extract_face_embedding_optimized(image_path, face_index)
                if embedding is None:
                    result['message'] = "无法从图片中提取人脸特征"
                    return result
                embedding = embedding.astype(np.float32)
                # 归一化后序列化为 bytes 存入 LONGBLOB / Normalize then serialize to bytes for LONGBLOB storage
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                embedding_bytes = embedding.tobytes()
                cursor.execute('''
                    INSERT INTO `user` (
                        person_id, name, height, weight, nationality,
                        face_embedding, face_confidence, face_quality, register_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    person_id, name, height, weight, nationality,
                    embedding_bytes,
                    face_info.get('confidence', 0), face_info.get('quality_score', 0),
                    datetime.now()
                ))
                self.conn.commit()
                self._embedding_cache[person_id] = embedding
                result['success'] = True
                result['message'] = f"人脸注册成功，ID: {person_id}"
                result['face_info'] = face_info
                logger.info(f"注册人脸成功: {person_id}")
        except Exception as e:
            self.conn.rollback()
            result['message'] = f"注册失败: {str(e)}"
            logger.error(f"注册人脸失败: {e}")
        return result

    def register_face_with_embedding(self, embedding: np.ndarray, face_info: Dict,
                                     person_id: str, image_path: str,
                                     name: str = '', company: str = '', height: str = '',
                                     weight: str = '', nationality: str = '') -> Dict:
        """人脸注册（外部特征向量）：直接使用调用方提供的 embedding 写入 MySQL / Register face with external embedding: write caller-provided embedding directly into MySQL.
        Returns: dict with keys success, person_id, message, face_info."""
        result = {'success': False, 'person_id': person_id, 'message': '', 'face_info': face_info}
        try:
            with self.lock.write_lock():
                cursor = self._get_cursor()
                cursor.execute('SELECT person_id FROM `user` WHERE person_id = %s', (person_id,))
                if cursor.fetchone():
                    result['message'] = f"Person ID '{person_id}' already exists"
                    return result
                embedding = embedding.astype(np.float32).flatten()
                if embedding.shape[0] != 512:
                    raise ValueError(f"输入特征维度不匹配。期望: 512, 实际: {embedding.shape[0]}")
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                embedding_bytes = embedding.tobytes()
                cursor.execute('''
                    INSERT INTO `user` (
                        person_id, name, company, height, weight, nationality,
                        face_embedding, face_confidence, face_quality, register_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    person_id, name, company, height, weight, nationality,
                    embedding_bytes,
                    face_info.get('confidence', 0), face_info.get('quality_score', 0),
                    datetime.now()
                ))
                self.conn.commit()
                self._embedding_cache[person_id] = embedding
                result['success'] = True
                result['message'] = f"人脸注册成功，ID: {person_id}"
                logger.info(f"特征注册成功 (使用特征向量): {person_id}")
        except Exception as e:
            self.conn.rollback()
            result['message'] = f"注册失败: {str(e)}"
            logger.error(f"注册失败: {e}", exc_info=True)
        return result

    def delete_face(self, person_id: str) -> Dict:
        """人脸删除：从 MySQL 删除记录并同步清除内存缓存 / Delete face: remove record from MySQL and sync memory cache eviction.
        Returns: dict with keys success, message."""
        result = {'success': False, 'message': '删除失败'}
        try:
            with self.lock.write_lock():
                cursor = self._get_cursor()
                cursor.execute('SELECT person_id FROM `user` WHERE person_id = %s', (person_id,))
                if not cursor.fetchone():
                    result['message'] = f"人员ID {person_id} 不存在"
                    result['success'] = True
                    return result
                cursor.execute('DELETE FROM `user` WHERE person_id = %s', (person_id,))
                self.conn.commit()
                self._embedding_cache.pop(person_id, None)
                result['success'] = True
                result['message'] = f"人员ID {person_id} 删除成功"
                logger.info(f"删除人脸成功: {person_id}")
        except Exception as e:
            self.conn.rollback()
            result['message'] = f"删除操作异常: {str(e)}"
            logger.error(f"删除人脸时发生异常: {e}", exc_info=True)
        return result

    def search_face(self, image_path: str, top_k: int = 5, threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
                    face_index: int = 0, embedding: np.ndarray = None,
                    alpha: float = DEFAULT_SIMILARITY_ALPHA,
                    gender_filter: Optional[str] = None) -> Dict:
        """人脸1:N搜索：提取查询特征后与内存缓存全量计算余弦相似度，返回 top_k 结果 / 1:N face search: extract query embedding, compute cosine similarity against memory cache, return top_k results.
        Returns: dict with keys success, matches(list), total_faces, face_info, pad_top, pad_left, message."""
        result = {
            'success': False,
            'query_image': image_path if image_path else 'embedding',
            'total_faces': 0,
            'matches': [],
            'message': '',
            'face_info': None,
            'pad_top': 0,
            'pad_left': 0,
        }
        try:
            with self.lock.read_lock():
                if not self._embedding_cache:
                    result['message'] = "人脸库为空"
                    return result
                query_vector = None
                pad_top, pad_left = 0, 0
                if image_path and os.path.exists(image_path):
                    with open(image_path, 'rb') as f:
                        img_data = f.read()
                    original_image = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
                    if original_image is None:
                        result['message'] = f"无法读取图片: {image_path}"
                        return result
                    padded_image, pad_top, pad_left = _pad_to_ratio(original_image)
                    detected_embedding, face_info = self.face_extractor.extract_face_embedding_from_array(padded_image, face_index)
                    if detected_embedding is None:
                        result['message'] = "无法从查询图片中提取人脸特征"
                        return result
                    result['face_info'] = face_info
                    result['pad_top'] = pad_top
                    result['pad_left'] = pad_left
                    # 若调用方同时传入 embedding，则优先使用调用方的向量 / Prefer caller-provided embedding if supplied
                    query_vector = (embedding if embedding is not None else detected_embedding).astype(np.float32)
                elif embedding is not None:
                    query_vector = embedding.astype(np.float32).flatten()
                else:
                    result['message'] = f"图片文件不存在: {image_path}"
                    return result
                norm = np.linalg.norm(query_vector)
                if norm > 0:
                    query_vector = query_vector / norm
                # Full-scan cosine similarity with non-linear alpha transform.
                # raw_similarity = dot product of normalized vectors (cosine similarity in [0,1])
                # transformed_similarity = raw_similarity ** alpha
                # alpha < 1 boosts mid-low scores (wider recall); alpha = 1 = no change.
                scored = []
                for pid, emb in self._embedding_cache.items():
                    raw_similarity = float(np.dot(query_vector, emb))
                    # Clamp to [0,1] before power transform (negative raw scores = no match)
                    raw_clamped = max(0.0, raw_similarity)
                    transformed_similarity = raw_clamped ** alpha
                    if transformed_similarity >= threshold:
                        scored.append((pid, transformed_similarity, raw_similarity))
                scored.sort(key=lambda x: x[1], reverse=True)
                scored = scored[:top_k]
                matches = []
                if scored:
                    cursor = self._get_cursor()
                    person_ids = [s[0] for s in scored]
                    fmt = ','.join(['%s'] * len(person_ids))
                    cursor.execute(f'''
                        SELECT person_id, name, height, weight, nationality, register_time
                        FROM `user` WHERE person_id IN ({fmt})
                    ''', person_ids)
                    db_rows = {row['person_id']: row for row in cursor.fetchall()}
                    for rank, (pid, transformed_similarity, raw_similarity) in enumerate(scored, start=1):
                        row = db_rows.get(pid)
                        if row:
                            matches.append({
                                'rank': rank,
                                'person_id': row['person_id'],
                                'name': row['name'],
                                'height': row['height'],
                                'weight': row['weight'],
                                'nationality': row['nationality'],
                                'similarity': transformed_similarity,
                                'raw_similarity': raw_similarity,
                                'register_time': str(row['register_time']),
                            })
                result['success'] = True
                result['total_faces'] = len(self._embedding_cache)
                result['matches'] = matches
                result['message'] = f"搜索完成，找到 {len(matches)} 个匹配结果"
                logger.info(f"人脸搜索完成: {len(matches)} 个匹配结果")
        except Exception as e:
            result['message'] = f"搜索失败: {str(e)}"
            logger.error(f"人脸搜索失败: {e}")
            traceback.print_exc()
        return result

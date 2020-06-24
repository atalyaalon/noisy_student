import os

TRAIN_SPLIT_PERCENTAGES = [0.333334, 0.5]
STUDENT_TEACHER_LOOP = 3
COCOSPLIT_PATH = os.getenv("COCOSPLIT_PATH")
ANNOTATIONS_DIR = os.getenv('ANNOTATIONS_DIR')
NEW_ANNOTATIONS_DIR = os.getenv('NEW_ANNOTATIONS_DIR')
ORIGINAL_ANNOTATIONS_DIR = os.getenv('ORIGINAL_ANNOTATIONS_DIR')
ORIGINAL_TRAIN_ANNOTATION_FILE = os.getenv('ORIGINAL_TRAIN_ANNOTATION_FILE')
ORIGINAL_VAL_ANNOTATION_FILE = os.getenv('ORIGINAL_VAL_ANNOTATION_FILE')
TRAIN_IMAGE_DIR = os.getenv('TRAIN_IMAGE_DIR')
VAL_IMAGE_DIR = os.getenv('VAL_IMAGE_DIR')
OUTPUT_DIR = os.getenv('OUTPUT_DIR')
EVAL_DIR = os.getenv('EVAL_DIR')
OPENPIFPAF_PATH = os.getenv('OPENPIFPAF_PATH')

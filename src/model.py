import os
import json
import pandas as pd
import logging
import boto3
from collections import defaultdict
from data_consts import OPENPIFPAF_PATH, MERGED_TRAIN_ANNOTATIONS_FILE_PREFIX
from consts import (EVAL_VAL_COMMAND,
                    EVAL_OTHER_COMMAND,
                    MOCK_RUN,
                    S3_BUCKET_NAME,
                    AWS_ACCESS_ID,
                    AWS_ACCESS_KEY)


class Model(object):
    def __init__(self, model_type, model_idx, num_train_epochs, train_image_dir, train_annotations, original_train_annotations, val_image_dir, val_annotations, next_gen_annotations, full_data_model=False):
        self._model_type = model_type
        self._model_idx = model_idx
        if full_data_model:
            model_output_file_suffix = '_full_training_data'
        else:
            model_output_file_suffix = ''
        self._model_output_file = 'model_type_{model_type}_model_no_{model_idx}'.format(model_idx=self._model_idx,
                                                                                        model_type=self._model_type) + model_output_file_suffix
        self._eval_output_file = 'eval_of_val_dataset_model_type_{model_type}_model_no_{model_idx}'.format(model_idx=self._model_idx,
                                                                                                           model_type=self._model_type) + model_output_file_suffix
        self._new_data_eval_file = 'eval_of_new_dataset_model_type_{model_type}_model_no_{model_idx}'.format(model_idx=self._model_idx,
                                                                                                             model_type=self._model_type) + model_output_file_suffix

        self._num_train_epochs = num_train_epochs
        self._train_image_dir = train_image_dir
        self._train_annotations = train_annotations
        self._original_train_annotations = original_train_annotations
        self._val_image_dir = val_image_dir
        self._val_annotations = val_annotations
        self._next_gen_annotations = next_gen_annotations
        self._selected_ann_data = None
        self.images_ids_for_next_gen_test = None
        self._merged_annotations_path = None

    def get_images_count_in_train_annotations_file(self):
        logging.info('Loading train annotations for counting images')
        with open(os.path.join(OPENPIFPAF_PATH, self._train_annotations), 'r') as j:
            train_ann_data = json.loads(j.read())
        images_count = len(train_ann_data['images'])
        logging.info('Threre are {images_count} images in train annotations file'.format(images_count=images_count))
        return images_count

    def fit(self):
        pass

    def create_val_score(self, metric='oks'):
        """
        creates val score files for val data
        """
        logging.info('Creating val scores of Model no.{model_idx}'.format(model_idx=self._model_idx))
        if metric == 'oks':
            checkpoint = self._model_output_file
            eval_process_return_value = os.system(EVAL_VAL_COMMAND.format(openpifpaf_path=OPENPIFPAF_PATH,
                                                                          model_output_file=checkpoint,
                                                                          dataset_image_dir=self._val_image_dir,
                                                                          dataset_annotations=self._val_annotations,
                                                                          eval_output_file=self._eval_output_file))
            if eval_process_return_value != 0:
                raise ValueError('Could not create val score - Eval of val failed')
            logging.info('eval_process_return_value:{return_value}'.format(return_value=eval_process_return_value))

    def select_new_images(self, thresh):
        logging.info('Loading new annotation file created by teacher')
        new_data_eval_pred_file_path = os.path.join(OPENPIFPAF_PATH, self._new_data_eval_file + '.pred.json')
        with open(new_data_eval_pred_file_path, 'r') as j:
            new_annotations_data = json.loads(j.read())

        logging.info('Collecting annotations scores per image')
        all_annotations_in_new_annotations_data = len(new_annotations_data)
        image_ann_scores = defaultdict(list)
        for ann_data in new_annotations_data:
            ann_score = ann_data['score']
            image_ann_scores[ann_data['image_id']].append(ann_score)

        logging.info('Filtering new annotations using the min score per image')
        df_ann_scores = pd.DataFrame.from_dict(image_ann_scores, orient='index').transpose()
        df_ann_scores_description = df_ann_scores.describe().T
        images_ids_filtered_by_min_score = list(df_ann_scores_description.loc[df_ann_scores_description['min'] > thresh].index.values)
        self.images_ids_for_next_gen_test = list(df_ann_scores_description.loc[df_ann_scores_description['min'] <= thresh].index.values)
        new_annotations_data_filtered_by_score = [ann for ann in new_annotations_data if ann['image_id'] in images_ids_filtered_by_min_score]

        logging.info('Loading original train annotations')
        with open(os.path.join(OPENPIFPAF_PATH, self._original_train_annotations), 'r') as j:
            train_ann_data = json.loads(j.read())
        logging.info('Find max_id in train annotations')
        max_id = 0
        mock_num_keypoints = 0
        mock_keypoints = None
        for idx, ann in enumerate(train_ann_data['annotations']):
            max_id = max(max_id, ann['id'])
            if MOCK_RUN == 'TRUE' and mock_num_keypoints == 0:
                mock_keypoints = ann['keypoints']
                mock_num_keypoints = ann['num_keypoints']

        logging.info('Load original next gen annotations file for additional info')
        next_gen_annotations_path = os.path.join(OPENPIFPAF_PATH, self._next_gen_annotations)
        with open(next_gen_annotations_path, 'r') as j:
            next_gen_annotations_data = json.loads(j.read())
        file_names = {}
        flickr_urls = {}
        for image in next_gen_annotations_data['images']:
            file_names[image['id']] = image.get('file_name')
            flickr_urls[image['id']] = image.get('flickr_url')

        logging.info('Create new annotations dict from new annotations')
        selected_ann_data = {'annotations': [], 'images': []}
        total_new_annotations_filtered_count = len(new_annotations_data_filtered_by_score)
        total_new_images_filtered_count = len(images_ids_filtered_by_min_score)
        logging.info('After filtering by thresh {thresh}, {count_annotations} annotations in {count_images} images are selected as new images out of {all} annotations'.format(thresh=thresh,
                                                                                                                                                                               count_annotations=total_new_annotations_filtered_count,
                                                                                                                                                                               count_images = total_new_images_filtered_count,
                                                                                                                                                                               all=all_annotations_in_new_annotations_data))
        added_images_ids = []
        for idx, ann in enumerate(new_annotations_data_filtered_by_score):
            if MOCK_RUN == 'TRUE' and idx % 20 == 0:
                ann['num_keypoints'] = mock_num_keypoints
                ann['keypoints'] = mock_keypoints
            else:
                ann['num_keypoints'] = sum([1 for i in ann['keypoints'][::3] if i > 0])
            ann['id'] = max_id + 1
            max_id += 1
            # add key, value iscrowd, 0
            ann['iscrowd'] = 0
            selected_ann_data['annotations'].append(ann)
            # add image_id if not exists
            if ann['image_id'] not in added_images_ids:
                selected_ann_data['images'].append({'id': ann['image_id'],
                                                    'file_name': file_names[ann['image_id']],
                                                    'flickr_url': flickr_urls[ann['image_id']]})
                added_images_ids.append(ann['image_id'])
        self._selected_ann_data = selected_ann_data

    def merge_annotations(self):
        with open(os.path.join(OPENPIFPAF_PATH, self._original_train_annotations), 'r') as j:
            train_ann_data = json.loads(j.read())
        if self._selected_ann_data:
            for key, value in train_ann_data.items():
                logging.info('merging key: {key}'.format(key=key))
                selected_ann_value = self._selected_ann_data.get(key)
                if selected_ann_value:
                    if isinstance(selected_ann_value, list):
                        value.extend(selected_ann_value)
                    else :
                        value.append(selected_ann_value)
        merged_file_name = os.path.join(OPENPIFPAF_PATH, '{prefix}_{model_idx}'.format(prefix=MERGED_TRAIN_ANNOTATIONS_FILE_PREFIX,
                                                                                       model_idx=self._model_idx+1))
        logging.info('Dumping File: {merged_file_name}'.format(merged_file_name=merged_file_name))
        with open(merged_file_name, 'w') as outfile:
            json.dump(train_ann_data, outfile)
        self._merged_annotations_path = merged_file_name

    def create_new_data_scores_and_annotations(self, thresh):
        """
        Creates next gen annotations and merges them with train annotations
        """
        if self._next_gen_annotations is not None and os.path.exists(self._next_gen_annotations):
            eval_process_new_data_return_value = os.system(EVAL_OTHER_COMMAND.format(openpifpaf_path=OPENPIFPAF_PATH,
                                                                                     model_output_file=self._model_output_file,
                                                                                     dataset_image_dir=self._train_image_dir,
                                                                                     dataset_annotations=self._next_gen_annotations,
                                                                                     eval_output_file=self._new_data_eval_file))
            if eval_process_new_data_return_value != 0:
                raise ValueError('Could not create val score - Eval of val failed')
            logging.info('eval_process_new_data_return_value:{return_value}'.format(return_value=eval_process_new_data_return_value))
            logging.info('select new images')
            self.select_new_images(thresh=thresh)
            logging.info('Merging annotations - creating annotation file for next generation')
            self.merge_annotations()
        else:
            logging.info('next_gen_annotations file does not exist - no more additional images for training')
            logging.info('Creating annotation file for next generation - consists of all train images of prev generation')
            self.merge_annotations()

    def save_results(self, experiment_name):
        logging.info('Starting Saving Results of Model {model_idx} in S3'.format(model_idx=self._model_idx))
        eval_output_stats_file_name = self._eval_output_file + '.stats.json'
        new_data_eval_stats_file_name = self._new_data_eval_file + '.stats.json'
        eval_output_pred_file_name = self._eval_output_file + '.pred.json'
        new_data_eval_pred_file_name = self._new_data_eval_file + '.pred.json'

        eval_output_stats_file_path = os.path.join(OPENPIFPAF_PATH, eval_output_stats_file_name)
        new_data_eval_stats_file_path = os.path.join(OPENPIFPAF_PATH, new_data_eval_stats_file_name)
        eval_output_pred_file_path = os.path.join(OPENPIFPAF_PATH, eval_output_pred_file_name)
        new_data_eval_pred_file_path = os.path.join(OPENPIFPAF_PATH, new_data_eval_pred_file_name)

        files = [(eval_output_stats_file_name, eval_output_stats_file_path),
                 (new_data_eval_stats_file_name, new_data_eval_stats_file_path),
                 (eval_output_pred_file_name, eval_output_pred_file_path),
                 (new_data_eval_pred_file_name, new_data_eval_pred_file_path)]
        s3 = boto3.resource('s3',
                            aws_access_key_id=AWS_ACCESS_ID,
                            aws_secret_access_key=AWS_ACCESS_KEY)
        for filename, filepath in files:
            if os.path.exists(filepath):
                logging.info('Uploading to Bucket {bucket_name}, Experiment {experiment_name}, Filename {filename}'.format(bucket_name=S3_BUCKET_NAME,
                                                                                                                           experiment_name=experiment_name,
                                                                                                                           filename=filename))
                s3.meta.client.upload_file(filepath, S3_BUCKET_NAME, os.path.join(experiment_name,filename))
        logging.info('Finished Saving Results of Model {model_idx} in S3'.format(model_idx=self._model_idx))

    def save_logs(self, experiment_name):
        logging.info('Starting Saving Logs of Model {model_idx} in S3'.format(model_idx=self._model_idx))
        filename = self._model_output_file + '.log'
        filepath = os.path.join(OPENPIFPAF_PATH, filename)
        s3 = boto3.resource('s3',
                            aws_access_key_id=AWS_ACCESS_ID,
                            aws_secret_access_key=AWS_ACCESS_KEY)
        if os.path.exists(filepath):
            logging.info('Uploading to Bucket {}, Experiment {}, Filename {}'.format(S3_BUCKET_NAME, experiment_name, filename))
            s3.meta.client.upload_file(filepath, S3_BUCKET_NAME, os.path.join(experiment_name,filename))
        logging.info('Finished Saving Logs of Model {model_idx} in S3'.format(model_idx=self._model_idx))

    def save_model(self, experiment_name):
        logging.info('Starting Saving Model {model_idx} in S3'.format(model_idx=self._model_idx))
        filename = self._model_output_file
        filepath = os.path.join(OPENPIFPAF_PATH, filename)
        s3 = boto3.resource('s3',
                            aws_access_key_id=AWS_ACCESS_ID,
                            aws_secret_access_key=AWS_ACCESS_KEY)
        if os.path.exists(filepath):
            logging.info('Uploading to Bucket {}, Experiment {}, Filename {}'.format(S3_BUCKET_NAME, experiment_name, filename))
            s3.meta.client.upload_file(filepath, S3_BUCKET_NAME, os.path.join(experiment_name,filename))
        logging.info('Finished Saving Model {model_idx} in S3'.format(model_idx=self._model_idx))

    def save_annotations(self, experiment_name):
        logging.info('Starting Saving Annotations {model_idx} in S3'.format(model_idx=self._model_idx))
        filename = '{prefix}_{model_idx}'.format(prefix=MERGED_TRAIN_ANNOTATIONS_FILE_PREFIX,
                                                 model_idx=self._model_idx+1)
        filepath = os.path.join(OPENPIFPAF_PATH, filename)
        s3 = boto3.resource('s3',
                            aws_access_key_id=AWS_ACCESS_ID,
                            aws_secret_access_key=AWS_ACCESS_KEY)
        if os.path.exists(filepath):
            logging.info('Uploading to Bucket {}, Experiment {}, Filename {}'.format(S3_BUCKET_NAME, experiment_name, filename))
            s3.meta.client.upload_file(filepath, S3_BUCKET_NAME, os.path.join(experiment_name,filename))
        logging.info('Finished Saving Annotations File {filename} in S3'.format(filename=filename))

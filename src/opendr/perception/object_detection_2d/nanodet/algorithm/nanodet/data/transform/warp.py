# Copyright 2021 RangiLyu.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
import random
from typing import Tuple

import cv2
import numpy as np
import torch


def get_flip_matrix(prob=0.5):
    F = np.eye(3)
    if random.random() < prob:
        F[0, 0] = -1
    return F


def get_perspective_matrix(perspective=0.0):
    """

    :param perspective:
    :return:
    """
    P = np.eye(3)
    P[2, 0] = random.uniform(-perspective, perspective)  # x perspective (about y)
    P[2, 1] = random.uniform(-perspective, perspective)  # y perspective (about x)
    return P


def get_rotation_matrix(degree=0.0):
    """

    :param degree:
    :return:
    """
    R = np.eye(3)
    a = random.uniform(-degree, degree)
    R[:2] = cv2.getRotationMatrix2D(angle=a, center=(0, 0), scale=1)
    return R


def get_scale_matrix(ratio=(1, 1)):
    """

    :param ratio:
    """
    Scl = np.eye(3)
    scale = random.uniform(*ratio)
    Scl[0, 0] *= scale
    Scl[1, 1] *= scale
    return Scl


def get_stretch_matrix(width_ratio=(1, 1), height_ratio=(1, 1)):
    """

    :param width_ratio:
    :param height_ratio:
    """
    Str = np.eye(3)
    Str[0, 0] *= random.uniform(*width_ratio)
    Str[1, 1] *= random.uniform(*height_ratio)
    return Str


def get_shear_matrix(degree):
    """

    :param degree:
    :return:
    """
    Sh = np.eye(3)
    Sh[0, 1] = math.tan(
        random.uniform(-degree, degree) * math.pi / 180
    )  # x shear (deg)
    Sh[1, 0] = math.tan(
        random.uniform(-degree, degree) * math.pi / 180
    )  # y shear (deg)
    return Sh


def get_translate_matrix(translate, width, height):
    """
    :param width:
    :param height:
    :param translate:
    :return:
    """
    T = np.eye(3)
    T[0, 2] = random.uniform(0.5 - translate, 0.5 + translate) * width  # x translation
    T[1, 2] = random.uniform(0.5 - translate, 0.5 + translate) * height  # y translation
    return T


def get_jitter_boxes(boxes, ratio=0.0, let_neg=True):
    """
    :param boxes:
    :param ratio: adjust each box boundary independently
    :param let_neg: let smaller than original boxes to be found
    :return:
    """
    x_min, y_min, x_max, y_max = (boxes[:, i] for i in range(4))
    width = x_max - x_min
    height = y_max - y_min
    y_center = y_min + height / 2.0
    x_center = x_min + width / 2.0

    neg_ratio = -ratio if let_neg else 0
    distortion = 1.0 + np.random.uniform(neg_ratio, ratio, boxes.shape)
    y_min_jitter = height * distortion[:, 0]
    x_min_jitter = width * distortion[:, 1]
    y_max_jitter = height * distortion[:, 2]
    x_max_jitter = width * distortion[:, 3]

    y_min, y_max = y_center - (y_min_jitter / 2.0), y_center + (y_max_jitter / 2.0)
    x_min, x_max = x_center - (x_min_jitter / 2.0), x_center + (x_max_jitter / 2.0)
    jitter_boxes = np.vstack((x_min, y_min, x_max, y_max)).T
    return jitter_boxes


def get_resize_matrix(raw_shape, dst_shape, keep_ratio):
    """
    Get resize matrix for resizing raw img to input size
    :param raw_shape: (width, height) of raw image
    :param dst_shape: (width, height) of input image
    :param keep_ratio: whether keep original ratio
    :return: 3x3 Matrix
    """
    r_w, r_h = raw_shape
    d_w, d_h = dst_shape
    Rs = np.eye(3)
    if keep_ratio:
        C = np.eye(3)
        C[0, 2] = -r_w / 2
        C[1, 2] = -r_h / 2

        if r_w / r_h < d_w / d_h:
            ratio = d_h / r_h
        else:
            ratio = d_w / r_w
        Rs[0, 0] *= ratio
        Rs[1, 1] *= ratio

        T = np.eye(3)
        T[0, 2] = 0.5 * d_w
        T[1, 2] = 0.5 * d_h
        return T @ Rs @ C
    else:
        Rs[0, 0] *= d_w / r_w
        Rs[1, 1] *= d_h / r_h
        return Rs


def get_hard_pos(img, bboxes, ratio):
    """
    Get resize matrix for resizing raw img to input size
    :param img: (width, height) of raw image
    :param bboxes: (width, height) of input image
    :param ratio: whether keep original
    :return: 3x3 Matrix
    """
    height = img.shape[0]  # shape(w,h,c)
    width = img.shape[1]

    mask_array = np.zeros_like(img)
    bigger_boxes = get_jitter_boxes(bboxes, ratio=ratio, let_neg=False)
    x_min, y_min, x_max, y_max = (bigger_boxes[:, i] for i in range(4))
    x_min = [int(x.clip(0, width)) for x in x_min]
    x_max = [int(x.clip(0, width)) for x in x_max]
    y_min = [int(x.clip(0, height)) for x in y_min]
    y_max = [int(x.clip(0, height)) for x in y_max]
    for x1, y1, x2, y2 in zip(x_min, y_min, x_max, y_max):
        mask_array[y1:y2, x1:x2] = 1
    return img * mask_array


def scriptable_warp_boxes(boxes, M, width, height):
    """
    Warp boxes function that uses pytorch api, so it can be used with scripting and tracing for optimization.
    """
    n = boxes.shape[0]
    if n:
        # warp points
        xy = torch.ones((n * 4, 3), dtype=torch.float32)
        xy[:, :2] = boxes[:, [0, 1, 2, 3, 0, 3, 2, 1]].reshape(
            n * 4, 2
        )  # x1y1, x2y2, x1y2, x2y1
        M = torch.transpose(M, 0, 1).float()
        xy = torch.mm(xy, M)  # transform
        xy = (xy[:, :2] / xy[:, 2:3]).reshape(n, 8)  # rescale
        # create new boxes
        x = xy[:, [0, 2, 4, 6]]
        y = xy[:, [1, 3, 5, 7]]
        xy = torch.cat((x.min(1).values, y.min(1).values, x.max(1).values, y.max(1).values)).reshape(4, n)
        xy = torch.transpose(xy, 0, 1).float()
        # clip boxes
        xy[:, [0, 2]] = xy[:, [0, 2]].clip(0, width)
        xy[:, [1, 3]] = xy[:, [1, 3]].clip(0, height)
        return xy
    else:
        return boxes


def filter_bboxes(boxes, classes, dst_shape, min_x=10, min_y=10, max_x=10, max_y=10):
    max_x, max_y = dst_shape[0] - max_x, dst_shape[1] - max_y
    filterd_boxes = np.empty([0, 4], dtype=np.float32)
    filterd_classes = np.array([], dtype=np.float32)
    for box, box_class in zip(boxes, classes):
        if box[0] > max_x or box[1] > max_y or box[2] < min_x or box[3] < min_y:
            continue
        filterd_boxes = np.vstack((filterd_boxes, box))
        filterd_classes = np.append(filterd_classes, box_class)
    return filterd_boxes, filterd_classes


def warp_boxes(boxes, M, width, height):
    n = len(boxes)
    if n:
        # warp points
        xy = np.ones((n * 4, 3))
        xy[:, :2] = boxes[:, [0, 1, 2, 3, 0, 3, 2, 1]].reshape(
            n * 4, 2
        )  # x1y1, x2y2, x1y2, x2y1
        xy = xy @ M.T  # transform
        xy = (xy[:, :2] / xy[:, 2:3]).reshape(n, 8)  # rescale
        # create new boxes
        x = xy[:, [0, 2, 4, 6]]
        y = xy[:, [1, 3, 5, 7]]
        xy = np.concatenate((x.min(1), y.min(1), x.max(1), y.max(1))).reshape(4, n).T
        # clip boxes
        xy[:, [0, 2]] = xy[:, [0, 2]].clip(0, width)
        xy[:, [1, 3]] = xy[:, [1, 3]].clip(0, height)
        return xy.astype(np.float32)
    else:
        return boxes


def get_minimum_dst_shape(
    src_shape: Tuple[int, int],
    dst_shape: Tuple[int, int],
    divisible: int = 0,
) -> Tuple[int, int]:
    """Calculate minimum dst shape"""
    src_w, src_h = src_shape
    dst_w, dst_h = dst_shape

    if src_w / src_h < dst_w / dst_h:
        ratio = dst_h / src_h
    else:
        ratio = dst_w / src_w

    dst_w = int(ratio * src_w)
    dst_h = int(ratio * src_h)

    if divisible and divisible > 0:
        dst_w = max(divisible, int((dst_w + divisible - 1) // divisible * divisible))
        dst_h = max(divisible, int((dst_h + divisible - 1) // divisible * divisible))
    return dst_w, dst_h


class ShapeTransform:
    """Shape transforms including resize, random perspective, random scale,
    random stretch, random rotation, random shear, random translate,
    and random flip.

    Args:
        keep_ratio: Whether to keep aspect ratio of the image.
        divisible: Make image height and width is divisible by a number.
        perspective: Random perspective factor.
        scale: Random scale ratio.
        stretch: Width and height stretch ratio range.
        rotation: Random rotate degree.
        shear: Random shear degree.
        translate: Random translate ratio.
        flip: Random flip probability.
        jitter_box: Random adjust box width and height.
    """

    def __init__(
        self,
        keep_ratio,
        divisible=0,
        perspective=0.0,
        scale=(1, 1),
        stretch=((1, 1), (1, 1)),
        rotation=0.0,
        shear=0.0,
        translate=0.0,
        flip=0.0,
        jitter_box: float = 0.0,
        hard_pos: float = 0.0,
        hard_pos_ratio: float = 0.0,
        **kwargs
    ):
        self.keep_ratio = keep_ratio
        self.divisible = divisible
        self.perspective = perspective
        self.scale_ratio = scale
        self.stretch_ratio = stretch
        self.rotation_degree = rotation
        self.shear_degree = shear
        self.flip_prob = flip
        self.translate_ratio = translate
        self.jitter_box_ratio = jitter_box
        self.hard_pos = hard_pos
        self.hard_pos_ratio = hard_pos_ratio

    def __call__(self, meta_data, dst_shape):
        raw_img = meta_data["img"]
        height = raw_img.shape[0]  # shape(h,w,c)
        width = raw_img.shape[1]

        # center
        C = np.eye(3)
        C[0, 2] = -width / 2
        C[1, 2] = -height / 2

        P = get_perspective_matrix(self.perspective)
        C = P @ C

        Scl = get_scale_matrix(self.scale_ratio)
        C = Scl @ C

        Str = get_stretch_matrix(*self.stretch_ratio)
        C = Str @ C

        R = get_rotation_matrix(self.rotation_degree)
        C = R @ C

        Sh = get_shear_matrix(self.shear_degree)
        C = Sh @ C

        F = get_flip_matrix(self.flip_prob)
        C = F @ C

        T = get_translate_matrix(self.translate_ratio, width, height)
        M = T @ C

        if self.keep_ratio:
            dst_shape = get_minimum_dst_shape(
                (width, height), dst_shape, self.divisible
            )

        ResizeM = get_resize_matrix((width, height), dst_shape, self.keep_ratio)
        M = ResizeM @ M
        img = cv2.warpPerspective(raw_img, M, dsize=tuple(dst_shape))
        if "gt_bboxes" in meta_data:
            boxes = get_jitter_boxes(meta_data["gt_bboxes"], self.jitter_box_ratio)
            boxes = warp_boxes(boxes, M, dst_shape[1], dst_shape[0])
            boxes, labels = filter_bboxes(boxes, meta_data["gt_labels"], (dst_shape[1], dst_shape[0]))
            if len(boxes) == 0:
                img = raw_img
                M = np.eye(3)
                boxes = meta_data["gt_bboxes"]
                labels = meta_data["gt_labels"]
            if random.uniform(0, 1) < self.hard_pos:
                img = get_hard_pos(img, boxes, self.hard_pos_ratio)
            meta_data["gt_bboxes"] = boxes
            meta_data["gt_labels"] = labels
        if "gt_masks" in meta_data:
            for i, mask in enumerate(meta_data["gt_masks"]):
                meta_data["gt_masks"][i] = cv2.warpPerspective(
                    mask, M, dsize=tuple(dst_shape)
                )
        meta_data["warp_matrix"] = M
        meta_data["img"] = img
        return meta_data

# coding: utf-8

from pathlib import Path

# Scientific modules imports
import numpy as np

# AxonDeepSeg imports
from AxonDeepSeg.morphometrics.compute_morphometrics import *
import AxonDeepSeg.ads_utils as ads


def launch_morphometrics_computation(path_img, path_prediction, axon_shape="circle"):
    """
    This function is equivalent to the morphometrics_extraction notebook of AxonDeepSeg.
    It automatically performs all steps (computations, savings, displays,...) of the
    morphometrics extraction of a given sample.
    :param path_img: path of the input image (microscopy sample)
    :param path_prediction: path of the segmented image (output of AxonDeepSeg)
    :param axon_shape: str: shape of the axon, can either be either be circle or an ellipse.
                            if shape of axon = 'circle', equivalent diameter is the diameter of the axon.
                            if shape of axon = 'ellipse', ellipse minor axis is the diameter of the axon.
    :return: none.
    """
    
    # If string, convert to Path objects
    path_img = convert_path(path_img)
    path_prediction = convert_path(path_prediction)

    try:
        # Read image
        img = ads.imread(path_img)

        # Read prediction
        pred = ads.imread(path_prediction)
    except (IOError, OSError) as e:
        print(("launch_morphometrics_computation: " + str(e)))
        raise
    else:

        # Get axon and myelin masks
        pred_axon = pred > 200
        pred_myelin = np.logical_and(pred >= 50, pred <= 200)

        # Get folder path
        path_folder = path_img.parent

        # Compute and save axon morphometrics
        stats_array = get_axon_morphometrics(pred_axon, path_folder, axon_shape=axon_shape)
        save_axon_morphometrics(path_folder, stats_array)

        # Generate and save displays of axon morphometrics
        fig = draw_axon_diameter(img, path_prediction, pred_axon, pred_myelin, axon_shape=axon_shape)
        save_map_of_axon_diameters(path_folder, fig)

        # Compute and save aggregate morphometrics
        aggregate_metrics = get_aggregate_morphometrics(
            pred_axon, pred_myelin, path_folder, axon_shape=axon_shape
        )
        write_aggregate_morphometrics(path_folder, aggregate_metrics)

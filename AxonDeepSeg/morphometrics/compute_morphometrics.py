# coding: utf-8

from pathlib import Path
from string import Template


# Scientific modules imports
import math
import numpy as np
from scipy import ndimage as ndi
from skimage import measure, morphology, feature

# Graphs and plots imports
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure

# AxonDeepSeg imports
from AxonDeepSeg.testing.segmentation_scoring import *
from AxonDeepSeg.ads_utils import convert_path



def get_pixelsize(path_pixelsize_file):
    """
    :param path_pixelsize_file: path of the txt file indicating the pixel size of the sample
    :return: the pixel size value.
    """
    
    # If string, convert to Path objects
    path_pixelsize_file = convert_path(path_pixelsize_file)

    try:
        with open(path_pixelsize_file, "r") as text_file:
            pixelsize = float(text_file.read())
    except IOError as e:

        print(("\nError: Could not open file \"{0}\" from "
               "directory \"{1}\".\n".format(path_pixelsize_file, Path.cwd())))
        raise
    except ValueError as e:
        print(("\nError: Pixel size data in file \"{0}\" is not valid – must "
               "be a plain text file with a single a numerical value (float) "
               " on the fist line.".format(path_pixelsize_file)))
        raise
    else:
        return pixelsize


def get_axon_morphometrics(im_axon, path_folder=None, im_myelin=None, pixel_size=None, axon_shape="circle"):
    """
    Find each axon and compute axon-wise morphometric data, e.g., equivalent diameter, eccentricity, etc.
    If a mask of myelin is provided, also compute myelin-related metrics (myelin thickness, g-ratio, etc.).
    :param im_axon: Array: axon binary mask, output of axondeepseg
    :param path_folder: str: absolute path of folder containing pixel size file
    :param im_myelin: Array: myelin binary mask, output of axondeepseg
    :param axon_shape: str: shape of the axon, can either be either be circle or an ellipse.
                            if shape of axon = 'circle', equivalent diameter is the diameter of the axon.
                            if shape of axon = 'ellipse', ellipse minor axis is the diameter of the axon.
    :return: Array(dict): dictionaries containing morphometric results for each axon
    """

    if path_folder is not None:
        # If string, convert to Path objects
        path_folder = convert_path(path_folder)

        pixelsize = get_pixelsize(path_folder / 'pixel_size_in_micrometer.txt')

    if (pixel_size  is not None) and (path_folder is None ):
        pixelsize = pixel_size

    stats_array = np.empty(0)
    # Label each axon object
    im_axon_label = measure.label(im_axon)
    # Measure properties for each axon object
    axon_objects = measure.regionprops(im_axon_label)

    # Deal with myelin mask
    if im_myelin is not None:

        im_axonmyelin = im_axon + im_myelin

        # Compute distance between each pixel and the background.
        distance = ndi.distance_transform_edt(im_axon)
        # Note: this distance is calculated from the im_axon,
        # note from the im_axonmyelin image, because we know that each axon
        # object is already isolated, therefore the distance metric will be
        # more useful for the watershed algorithm below.

        # Get axon centroid as int (not float) to be used as index
        ind_centroid = ([int(props.centroid[0]) for props in axon_objects],
                        [int(props.centroid[1]) for props in axon_objects])

        # Create an image with axon centroids, which value corresponds to the value of the axon object
        im_centroid = np.zeros_like(im_axon, dtype='uint16')
        for i in range(len(ind_centroid[0])):
            # Note: The value "i" corresponds to the label number of im_axon_label
            im_centroid[ind_centroid[0][i], ind_centroid[1][i]] = i + 1

        # Watershed segmentation of axonmyelin using distance map
        im_axonmyelin_label = morphology.watershed(-distance, im_centroid, mask=im_axonmyelin)
        # Measure properties of each axonmyelin object
        axonmyelin_objects = measure.regionprops(im_axonmyelin_label)

    # Create list of the exiting labels
    if im_myelin is not None:
        axonmyelin_labels_list = [axm.label for axm in axonmyelin_objects]

    # Loop across axon property and fill up dictionary with morphometrics of interest
    for prop_axon in axon_objects:
        # Centroid
        y0, x0 = prop_axon.centroid
        # Solidity
        solidity = prop_axon.solidity
        # Eccentricity
        eccentricity = prop_axon.eccentricity
        if axon_shape == "circle":
            # Axon equivalent diameter in micrometers
            axon_diam = prop_axon.equivalent_diameter * pixelsize
        else: 
            # Axon diameter using ellipse minor axis in micrometers
            axon_diam = prop_axon.minor_axis_length * pixelsize
        # Axon area in µm^2
        axon_area = prop_axon.area * (pixelsize ** 2)
        # Axon orientation angle
        orientation = prop_axon.orientation
        # Add metrics to list of dictionaries
        stats = {'y0': y0,
                 'x0': x0,
                 'axon_diam': axon_diam,
                 'axon_area': axon_area,
                 'solidity': solidity,
                 'eccentricity': eccentricity,
                 'orientation': orientation}

        # Deal with myelin
        if im_myelin is not None:
            # Find label of axonmyelin corresponding to axon centroid
            label_axonmyelin = im_axonmyelin_label[int(y0), int(x0)]

            if label_axonmyelin:
                idx = axonmyelin_labels_list.index(label_axonmyelin)
                prop_axonmyelin = axonmyelin_objects[idx]

                _res1 = evaluate_myelin_thickness_in_px(prop_axon, prop_axonmyelin, axon_shape)
                myelin_thickness = pixelsize * _res1

                _res2 = evaluate_myelin_area_in_px(prop_axon, prop_axonmyelin)
                myelin_area = (pixelsize ** 2) * _res2

                axonmyelin_area = (pixelsize ** 2) * prop_axonmyelin.area

                stats['myelin_thickness'] = myelin_thickness
                stats['myelin_area'] = myelin_area
                stats['axonmyelin_area'] = axonmyelin_area
                stats['gratio'] = (axon_diam / 2) / (axon_diam / 2 + myelin_thickness)
            else:
                print(
                    "WARNING: Myelin object not found for axon" +
                    "centroid [y:{0}, x:{1}]".format(y0, x0)
                    )

        stats_array = np.append(stats_array, [stats], axis=0)

    return stats_array

def evaluate_myelin_thickness_in_px(axon_object, axonmyelin_object, axon_shape):
    """
    Returns the  thickness of a myelin ring around an axon of a
    given equivalent diameter (see note [1] below) or minimum axis diameter of an ellipse. The result is in pixels.
    :param axon_object (skimage.measure._regionprops): object returned after
        measuring a axon labeled region
    :param axonmyelin_object (skimage.measure._regionprops): object returned after
        measuring a axon with myelin labeled region
    :param axon_shape: str: shape of the axon, can either be either be circle or an ellipse.
                            if shape of axon = 'circle', equivalent diameter is the diameter of the axon.
                            if shape of axon = 'ellipse', ellipse minor axis is the diameter of the axon.
    
    [1] According to https://scikit-image.org/docs/dev/api/skimage.measure.html?highlight=region%20properties#regionprops,
    the equivalent diameter is the diameter of a circle with the same area as
    the region.
    """
    attribute = "equivalent_diameter" if axon_shape == "circle" else "minor_axis_length" 
    warn_if_measures_are_unexpected(
        axon_object,
        axonmyelin_object,
        attribute
        )
    if axon_shape == "circle": 
        axon_diam = axon_object.equivalent_diameter
        axonmyelin_diam = axonmyelin_object.equivalent_diameter
    else: 
        axon_diam = axon_object.minor_axis_length
        axonmyelin_diam = axonmyelin_object.minor_axis_length
    return (axonmyelin_diam - axon_diam)/2

def evaluate_myelin_area_in_px(axon_object, axonmyelin_object):
    """
    Returns the myenlinated axon area minus the axon area.
    :param axon_object (skimage.measure._regionprops): object returned after
    measuring an axon labeled  region
    :param axonmyelin_object (skimage.measure._regionprops): object returned after
    measuring a axon with myelin labeled region
    """
    warn_if_measures_are_unexpected(
        axon_object,
        axonmyelin_object,
        "area"
        )
    return axonmyelin_object.area - axon_object.area

def warn_if_measures_are_unexpected(axon_object, axonmyelin_object, attribute):
    """
    Calls the `_check_measures_are_relatively_valid` function and if return
    value is False, print a warning.
    """
    checked = _check_measures_are_relatively_valid(axon_object, axonmyelin_object, attribute)
    if checked is False:
        x_a, y_a = axon_object.centroid
        data = {
            "attribute": attribute,
            "axon_label": axon_object.label,
            "x_ax": x_a,
            "y_ax": y_a,
            "axonmyelin_label": axonmyelin_object.label,
        }
        
        warning_msg = Template(
            "Warning, axon #$axon_label at [y:$y_ax, x:$x_ax] and " +
            "corresponding myelinated axon #$axonmyelin_label " +
            "have unexpected measure values for $attribute attributest."
            )
        print(warning_msg.safe_substitute(data))

def _check_measures_are_relatively_valid(axon_object, axonmyelin_object, attribute):
    """
    Checks if the attribute is positive and if the myelinated axon has a greater value
    """
    val_axon = getattr(axon_object, attribute)
    val_axonmyelin = getattr(axonmyelin_object, attribute)
    if val_axon > 0 and val_axonmyelin > 0 and val_axonmyelin > val_axon:
        return True
    else:
        return False

def save_axon_morphometrics(path_folder, stats_array):
    """
    :param path_folder: absolute path of the sample and the segmentation folder
    :param stats_array: list of dictionaries containing axon morphometrics
    :return:
    """
    
    # If string, convert to Path objects
    path_folder = convert_path(path_folder)
    
    try:
        np.save(str(path_folder / 'axonlist.npy'), stats_array)
    except IOError as e:
        print(("\nError: Could not save file \"{0}\" in "
               "directory \"{1}\".\n".format('axonlist.npy', path_folder)))
        raise


def load_axon_morphometrics(path_folder):
    """
    :param path_folder: absolute path of the sample and the segmentation folder
    :return: stats_array: list of dictionaries containing axon morphometrics
    """
    
    # If string, convert to Path objects
    path_folder = convert_path(path_folder)

    try:
        stats_array = np.load(str(path_folder / 'axonlist.npy'), allow_pickle=True)
    except IOError as e:
        print(("\nError: Could not load file \"{0}\" in "
               "directory \"{1}\".\n".format('axonlist.npy', path_folder)))
        raise
    else:
        return stats_array


def draw_axon_diameter(img, path_prediction, pred_axon, pred_myelin, axon_shape="circle"):
    """
    :param img: sample grayscale image (png)
    :param path_prediction: full path to the segmented file (*_seg-axonmyelin.png)
        from axondeepseg segmentation output
    :param pred_axon: axon mask from axondeepseg segmentation output
    :param pred_myelin: myelin mask from axondeepseg segmentation output
    :param axon_shape: str: shape of the axon, can either be either be circle or an ellipse.
                            if shape of axon = 'circle', equivalent diameter is the diameter of the axon.
                            if shape of axon = 'ellipse', ellipse minor axis is the diameter of the axon.
    :return: matplotlib.figure.Figure
    """
    
    # If string, convert to Path objects
    path_prediction = convert_path(path_prediction)

    path_folder = path_prediction.parent

    stats_array = get_axon_morphometrics(pred_axon, path_folder, axon_shape=axon_shape)
    axon_diam_list = [d["axon_diam"] for d in stats_array]
    axon_diam_array = np.asarray(axon_diam_list)

    labels = measure.label(pred_axon)
    axon_diam_display = np.zeros((np.shape(labels)[0], np.shape(labels)[1]))

    for pix_x in np.arange(np.shape(labels)[0]):
        for pix_y in np.arange(np.shape(labels)[1]):
            if labels[pix_x, pix_y] != 0:
                axon_diam_display[pix_x, pix_y] = axon_diam_array[
                    labels[pix_x, pix_y] - 1
                ]

    # Axon overlay on original image + myelin display (same color for every
    # myelin sheath)
    fig = Figure(figsize=(12, 9))
    FigureCanvas(fig)
    ax = fig.subplots()
    ax.imshow(img, cmap="gray", alpha=0.8)
    ax.imshow(pred_myelin, cmap="gray", alpha=0.3)
    im = ax.imshow(axon_diam_display, cmap="hot", alpha=0.5)
    fig.colorbar(im, fraction=0.03, pad=0.02)
    ax.set_title(
        "Axon overlay (colorcoded with axon diameter in um) and myelin display",
        fontsize=12,
    )
    return fig


def save_map_of_axon_diameters(path_folder, axon_diameter_figure):
    """
    :param path_folder: absolute path of the sample and the segmentation folder
    :param axon_diameter_figure: figure create with draw_axon_diameter
    :return: None
    """
    
    # If string, convert to Path objects
    path_folder = convert_path(path_folder)
    
    file_path = path_folder / "AxonDeepSeg_map-axondiameter.png"
    axon_diameter_figure.savefig(file_path)


def get_aggregate_morphometrics(pred_axon, pred_myelin, path_folder, axon_shape="circle"):
    """
    :param pred_axon: axon mask from axondeepseg segmentation output
    :param pred_myelin: myelin mask from axondeepseg segmentation output
    :param path_folder: absolute path of folder containing pixel size file
    :param axon_shape: str: shape of the axon, can either be either be circle or an ellipse.
                            if shape of axon = 'circle', equivalent diameter is the diameter of the axon.
                            if shape of axon = 'ellipse', ellipse minor axis is the diameter of the axon.
    :return: aggregate_metrics: dictionary containing values of aggregate metrics
    """

    # If string, convert to Path objects
    path_folder = convert_path(path_folder)

    # Compute AVF (axon volume fraction) = area occupied by axons in sample
    avf = np.count_nonzero(pred_axon) / float((pred_axon.size))
    # Compute MVF (myelin volume fraction) = area occupied by myelin sheaths in sample
    mvf = np.count_nonzero(pred_myelin) / float((pred_myelin.size))

    # Estimate aggregate g-ratio = sqrt(1/(1+MVF/AVF))
    gratio = math.sqrt(1 / (1 + (float(mvf) / float(avf))))

    # Get individual axons metrics and compute mean axon diameter
    stats_array = get_axon_morphometrics(pred_axon, path_folder, axon_shape=axon_shape)
    axon_diam_list = [d["axon_diam"] for d in stats_array]
    mean_axon_diam = np.mean(axon_diam_list)

    # Estimate mean myelin diameter (axon+myelin diameter) by using
    # aggregate g-ratio = mean_axon_diam/mean_myelin_diam

    mean_myelin_diam = mean_axon_diam / gratio

    # Estimate mean myelin thickness = mean_myelin_radius - mean_axon_radius
    mean_myelin_thickness = (float(mean_myelin_diam) / 2) - (float(mean_axon_diam) / 2)

    # Compute axon density (number of axons per mm2)
    px_size_um = get_pixelsize(path_folder / 'pixel_size_in_micrometer.txt')
    img_area_mm2 = float(pred_axon.size) * px_size_um * px_size_um / (float(1000000))
    axon_density_mm2 = float(len(axon_diam_list)) / float(img_area_mm2)

    # Create disctionary to store aggregate metrics
    aggregate_metrics = {'avf': avf, 'mvf': mvf, 'gratio_aggr': gratio, 'mean_axon_diam': mean_axon_diam,
                         'mean_myelin_diam': mean_myelin_diam, 'mean_myelin_thickness': mean_myelin_thickness,
                         'axon_density_mm2': axon_density_mm2}
    return aggregate_metrics


def write_aggregate_morphometrics(path_folder, aggregate_metrics):
    """
    :param path_folder: absolute path of folder containing sample + segmentation
    :param aggregate_metrics: dictionary containing values of aggregate metrics
    :return: nothing
    """
    
    # If string, convert to Path objects
    path_folder = convert_path(path_folder)
    
    try:
        with open(path_folder / 'aggregate_morphometrics.txt', 'w') as text_file:
            text_file.write('aggregate_metrics: ' + repr(aggregate_metrics) + '\n')
    except IOError as e:
        print(("\nError: Could not save file \"{0}\" in "
               "directory \"{1}\".\n".format('aggregate_morphometrics.txt', path_folder)))
        raise

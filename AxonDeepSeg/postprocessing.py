""""
Tools for the FSLeyes plugin.
"""
from skimage import measure, morphology, feature
from PIL import Image, ImageDraw, ImageOps, ImageFont
import numpy as np
import AxonDeepSeg.params
from matplotlib import rcParams
import os

def get_centroids(mask):
    """
    This function is used to find the centroids of objects found in the mask
    :param mask: the binary mask.
    :type mask: ndarray
    :return: a list containing the coordinates of the centroid of every object
    :rtype: list of int
    """
    # Label each object
    object_label = measure.label(mask)
    # Find the centroids of the objects
    objects = measure.regionprops(object_label)
    ind_centroid = (
        [int(props.centroid[0]) for props in objects],
        [int(props.centroid[1]) for props in objects],
    )
    return ind_centroid

def floodfill_axons(myelin_array):
    """
    This function does a floodfill operation on the myelin_array. The seed points are the centroids of the myelin
    objects. The goal is to fill the center of the myelin objects with the axon mask.
    Note: The myelin objects need to be closed in order to prevent the axon_mask from flooding the entire image.
    The myelin objects also need to be separated from each other, otherwise they will be counted as one object.
    :param myelin_array: the binary array corresponding to the myelin mask
    :return: the binary axon array corresponding to the axon mask after the floodfill
    """
    # Get the centroid indexes
    centroid_index_map = get_centroids(myelin_array)

    # Create an image with the myelinMask and floodfill at the coordinates of the centroids
    # Note: The floodfill algorithm only works on RGB images. Thus, the mask must be colorized before applying
    # the floodfill. Then, the array corresponding to the floodfilled color can be extracted.
    myelin_image = Image.fromarray(myelin_array * 255)
    myelin_image = ImageOps.colorize(
        myelin_image, (0, 0, 0, 255), (255, 255, 255, 255)
    )
    for i in range(len(centroid_index_map[0])):
        ImageDraw.floodfill(
            myelin_image,
            xy=(centroid_index_map[1][i], centroid_index_map[0][i]),
            value=(127, 127, 127, 255),
        )

    # Extract the axon_mask overlay
    axon_extracted_array = np.array(myelin_image.convert("LA"))
    axon_extracted_array = axon_extracted_array[:, :, 0]
    axon_extracted_array = np.equal(
        axon_extracted_array, 127 * np.ones_like(axon_extracted_array)
    )
    axon_extracted_array = axon_extracted_array.astype(np.uint8)
    return axon_extracted_array

def remove_intersection(mask_1, mask_2, priority=1, return_overlap=False):
    """
    This function removes the overlap between two masks on one of those two masks depending on the priority parameter.
    :param mask_1: First mask, with an intersecting section with the sectond one. The mask must contain values of 1 or 0
    only.
    :param mask_2: Second mask, with an intersecting section with the first one. The mask must contain values of 1 or 0
    only.
    :param priority (optional): Tells which of the two arrays should be kept. Can only be 1 or 2.
    :type priority: int
    :param return_overlap (optional): If set to True, the overlap mask will be returned.
    :type return_overlap: bool
    :return split_mask_1: First mask, minus the intersection if it doesn't have priority
    :return split_mask_2: Sectond mask, minus the intersection if it doesn't have priority
    :return return_overlap: A mask corresponding to the intersection of the two masks
    """

    if priority not in [1, 2]:
        raise Exception("Parameter priority can only be 1 or 2")

    array_1 = mask_1.astype(np.bool)
    array_2 = mask_2.astype(np.bool)
    intersection = (array_1 & array_2).astype(np.uint8)

    if priority is 1:
        mask_2 = mask_2 - intersection
    if priority is 2:
        mask_1 = mask_1 - intersection

    if return_overlap is True:
        return mask_1, mask_2, intersection
    else:
        return mask_1, mask_2

def generate_axon_numbers_image(centroid_index, x0_array, y0_array, image_size, mean_axon_diameter_in_pixels=None):
    """
    This function generates an image where the numbers in centroid_index are at their corresponding location specified
    by their coordinates (x0, y0)
    :param centroid_index: The array containing the axon numbers.
    :type centroid_index: numpy array
    :param x0_array: X coordinate of the centroids
    :type x0_array: numpy array
    :param y0_array: Y coordinate of the centroids
    :type y0_array: numpy array
    :param image_size: the size of the image
    :type image_size: tuple
    :param mean_axon_diameter_in_pixels (optional): the mean axon diameter of the axon mask. If this parameter
    is passed, the font size will be determined based on it. Otherwise, the image size will be used to determine
    the font size.
    :return: the binary image with the numbers at their corresponding coordinate.
    """

    # Create an empty image which will contain the binary image
    number_image = Image.new(mode='L', size=image_size, color=0)
    draw = ImageDraw.Draw(number_image)

    # Use a font from the matplotlib package
    # The size of the font depends on the dimensions of the image, should be at least 10
    # If the the mean_axon_diameter is specified, use it to determine the font_size
    font_path = os.path.join(rcParams["datapath"], "fonts/ttf/DejaVuSans.ttf")
    if mean_axon_diameter_in_pixels is None:
        font_size = max(int(sum(image_size) * 0.5 * 0.01), 10)
    else:
        font_size = max(int(mean_axon_diameter_in_pixels / 3), 10)
    font = ImageFont.truetype(font=font_path, size=font_size)

    # Fill the image with the numbers at their corresponding coordinates
    for i in range(centroid_index.size):
        draw.text(xy=(x0_array[i] - font_size/2, y0_array[i] - font_size/2),
                  text=str(centroid_index[i]), font=font, fill=AxonDeepSeg.params.intensity['binary'])

    # Transform the image into a numpy array
    image_array = np.asarray(number_image)

    return image_array.astype(np.uint8)

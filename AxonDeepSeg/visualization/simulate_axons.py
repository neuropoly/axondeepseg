"""Simulate axons as histology slides
This module is for simulating axons as an image of a histology slide.
  Typical usage example:
    from AxonDeepSeg.visualization.simulate_axons import SimulateAxons

    obj=SimulateAxons()

    obj.generate_axon(axon_radius=40, center=[100, 100], gratio=0.6, plane_angle=0)
    obj.generate_axon(axon_radius=40, center=[300, 300], gratio=0.6, plane_angle=25)
    obj.generate_axon(axon_radius=40, center=[500, 500], gratio=0.6, plane_angle=50)
    obj.generate_axon(axon_radius=40, center=[700, 700], gratio=0.6, plane_angle=75)

    obj.save()
"""

import numpy as np
import numpy as np
from scipy.ndimage import rotate
import imageio
import AxonDeepSeg.ads_utils


class SimulateAxons:
    """Axon simulation class.
    Simulates an image of a histology slide of axons.
    Attributes:
        image: Numpy array of the simulation.
    """

    def __init__(self, image_dims=[1000, 1000]):
        """Initializes an SimulateAxons object.
        Assigns the dimensions of the image to the `width` and `height` attribute,
        sets the `origin` attribute for the center of the image, and initializes
        the `image`` attribute.
        Args:
        image_dims: [width, height] in number of pixels.
        Returns:
            SimulateAxons class object with parameters initialized.
        """

        self.width = image_dims[0]
        self.height = image_dims[1]
        self.origin = [self.width / 2, self.height / 2]

        # Initialize image
        self.image = np.zeros([self.width, self.height], dtype=np.uint8)

    def generate_axon(
        self,
        axon_radius,
        center=None,
        gratio=0.7,
        plane_angle=0,
    ):
        """Generates an axon and adds it to the image.
        Args:
        axon_radius: radius of the axon in number of pixels.
        center: pixel location of the center of the axon. [0, 0] is top left of
                the image.
        gratio: g-ratio of the axon. Determines the myelin thickness.
            gratio = (axon_radius)/(axon_radius+myelin thickness)
        plane_angle: Degrees. Angle of the plane cutting through the angle.
            Makes axons ellipsoidal in nature.
        """

        if center is None:
            center = self.origin

        x = np.arange(0, self.width)
        y = np.arange(0, self.height)

        myelin_thickness = calc_myelin_thickness(axon_radius, gratio)

        axon_major_axis_radius = axon_radius / np.cos(np.deg2rad(plane_angle))
        axon_minor_axis_radius = axon_radius

        myelin_major_axis_radius = (axon_radius + myelin_thickness) / np.cos(
            np.deg2rad(plane_angle)
        )
        myelin_minor_axis_radius = axon_radius + myelin_thickness

        axon = (x[np.newaxis, :] - center[0]) ** 2 / (axon_major_axis_radius ** 2) + (
            y[:, np.newaxis] - center[1]
        ) ** 2 / (axon_minor_axis_radius ** 2) < 1
        myelin_outer = (x[np.newaxis, :] - center[0]) ** 2 / (
            myelin_major_axis_radius ** 2
        ) + (y[:, np.newaxis] - center[1]) ** 2 / (myelin_minor_axis_radius ** 2) < 1

        myelin = myelin_outer ^ axon

        # Convert to int before rotate
        axon = np.ndarray.astype(axon, int)
        myelin = np.ndarray.astype(myelin, int)

        # Convert back to bool
        axon = np.ndarray.astype(axon, bool)
        myelin = np.ndarray.astype(myelin, bool)

        self.image[axon & (self.image == 0)] = 255
        self.image[myelin & (self.image == 0)] = 127

    def save(self, filename="SimulatedAxons.png"):
        imageio.imwrite(filename, self.image)

    def reset(self):
        self.image = np.zeros([self.width, self.height], dtype=np.uint8)

def calc_myelin_thickness(axon_radius, gratio):

    return axon_radius * (1/gratio-1)

"""
This is an FSLeyes plugin script that integrates AxonDeepSeg tools into FSLeyes.

Author : Stoyan I. Asenov
"""

import wx
import wx.lib.agw.hyperlink as hl

import fsleyes.controls.controlpanel as ctrlpanel
import fsleyes.actions.loadoverlay as ovLoad

import numpy as np
import nibabel as nib
from PIL import Image, ImageDraw, ImageOps
import scipy.misc
import json
from pathlib import Path

import AxonDeepSeg
from AxonDeepSeg.apply_model import axon_segmentation
from AxonDeepSeg.segment import segment_image
import AxonDeepSeg.morphometrics.compute_morphometrics as compute_morphs
from AxonDeepSeg import postprocessing, params, ads_utils
from config import axonmyelin_suffix, axon_suffix, myelin_suffix

import math
from scipy import ndimage as ndi
from skimage import measure, morphology, feature

import tempfile
import openpyxl
import pandas as pd
import imageio

from AxonDeepSeg.morphometrics.compute_morphometrics import *

VERSION = "0.2.15"

class ADScontrol(ctrlpanel.ControlPanel):
    """
    This class is the object corresponding to the AxonDeepSeg control panel.
    """

    def __init__(self, ortho, *args, **kwargs):
        """
        This function initializes the control panel. It generates the widgets and adds them to the panel. It also sets
        the initial position of the panel to the left
        :param ortho: This is used to access the ortho ops in order to turn off the X and Y canvas as well as the cursor
        """
        ctrlpanel.ControlPanel.__init__(self, ortho, *args, **kwargs)

        # Add a sizer to the control panel
        # This sizer will contain the buttons
        sizer_h = wx.BoxSizer(wx.VERTICAL)

        # Add the logo to the control panel
        ADS_logo = self.get_logo()
        sizer_h.Add(ADS_logo, flag=wx.SHAPED, proportion=1)

        # Add the citation to the control panel
        citation_box = wx.TextCtrl(
            self, value=self.get_citation(), size=(100, 50), style=wx.TE_MULTILINE
        )
        sizer_h.Add(citation_box, flag=wx.SHAPED, proportion=1)

        # Add a hyperlink to the documentation
        hyper = hl.HyperLinkCtrl(
            self, -1, label="Need help? Read the documentation", URL="https://axondeepseg.readthedocs.io/en/latest/"
        )
        sizer_h.Add(hyper, flag=wx.SHAPED, proportion=1)

        # Define the color of button labels
        button_label_color = (0, 0, 0)

        # Add the image loading button
        load_png_button = wx.Button(self, label="Load PNG or TIF file")
        load_png_button.SetForegroundColour(button_label_color)
        load_png_button.Bind(wx.EVT_BUTTON, self.on_load_png_button)
        load_png_button.SetToolTip(wx.ToolTip("Loads a .png or .tif file into FSLeyes"))
        sizer_h.Add(load_png_button, flag=wx.SHAPED, proportion=1)

        # Add the mask loading button
        load_mask_button = wx.Button(self, label="Load existing mask")
        load_mask_button.SetForegroundColour(button_label_color)
        load_mask_button.Bind(wx.EVT_BUTTON, self.on_load_mask_button)
        load_mask_button.SetToolTip(
            wx.ToolTip(
                "Loads an existing axonmyelin mask into FSLeyes. "
                "The selected image should contain both the axon and myelin masks. "
                "The regions on the image should have an intensity of 0 for the background, "
                "127 for the myelin and 255 for the axons. "
            )
        )
        sizer_h.Add(load_mask_button, flag=wx.SHAPED, proportion=1)

        # Add the model choice combobox
        self.model_combobox = wx.ComboBox(
            self,
            choices=ads_utils.get_existing_models_list(),
            size=(100, 20),
            value="Select the modality",
        )
        self.model_combobox.SetForegroundColour(button_label_color)
        self.model_combobox.SetToolTip(
            wx.ToolTip("Select the modality used to acquire the image")
        )
        sizer_h.Add(self.model_combobox, flag=wx.SHAPED, proportion=1)

        # Add the button that applies the prediction model
        apply_model_button = wx.Button(self, label="Apply ADS prediction model")
        apply_model_button.SetForegroundColour(button_label_color)
        apply_model_button.Bind(wx.EVT_BUTTON, self.on_apply_model_button)
        apply_model_button.SetToolTip(
            wx.ToolTip("Applies the prediction model and displays the masks")
        )
        sizer_h.Add(apply_model_button, flag=wx.SHAPED, proportion=1)

        # The Watershed button's purpose isn't clear. It is unavailable for now.

        # # Add the button that runs the watershed algorithm
        # run_watershed_button = wx.Button(self, label="Run Watershed")
        # run_watershed_button.Bind(wx.EVT_BUTTON, self.on_run_watershed_button)
        # run_watershed_button.SetToolTip(
        #     wx.ToolTip(
        #         "Uses a watershed algorithm to find the different axon+myelin"
        #         "objects. This is used to see if where are connections"
        #         " between two axon+myelin objects."
        #     )
        # )
        # sizer_h.Add(run_watershed_button, flag=wx.SHAPED, proportion=1)

        # Add the fill axon tool
        fill_axons_button = wx.Button(self, label="Fill axons")
        fill_axons_button.SetForegroundColour(button_label_color)
        fill_axons_button.Bind(wx.EVT_BUTTON, self.on_fill_axons_button)
        fill_axons_button.SetToolTip(
            wx.ToolTip(
                "Automatically fills the axons inside myelin objects."
                " THE MYELIN OBJECTS NEED TO BE CLOSED AND SEPARATED FROM EACH "
                "OTHER (THEY MUST NOT TOUCH) FOR THIS TOOL TO WORK CORRECTLY."
            )
        )
        sizer_h.Add(fill_axons_button, flag=wx.SHAPED, proportion=1)

        # Add the save Segmentation button
        save_segmentation_button = wx.Button(self, label="Save segmentation")
        save_segmentation_button.SetForegroundColour(button_label_color)
        save_segmentation_button.Bind(wx.EVT_BUTTON, self.on_save_segmentation_button)
        save_segmentation_button.SetToolTip(
            wx.ToolTip("Saves the axon and myelin masks in the selected folder")
        )
        sizer_h.Add(save_segmentation_button, flag=wx.SHAPED, proportion=1)

        # Add compute morphometrics button
        compute_morphometrics_button = wx.Button(self, label="Compute morphometrics")
        compute_morphometrics_button.SetForegroundColour(button_label_color)
        compute_morphometrics_button.Bind(wx.EVT_BUTTON, self.on_compute_morphometrics_button)
        compute_morphometrics_button.SetToolTip(
            wx.ToolTip(
                "Calculates and saves the morphometrics to an excel and csv file. "
                "Shows the numbers of the axons at the coordinates specified in the morphometrics file."
            )
        )
        sizer_h.Add(compute_morphometrics_button, flag=wx.SHAPED, proportion=1)

        # Set the sizer of the control panel
        self.SetSizer(sizer_h)

        # Initialize the variables that are used to track the active image
        self.png_image_name = []
        self.image_dir_path = []
        self.most_recent_watershed_mask_name = None

        # Toggle off the X and Y canvas
        oopts = ortho.sceneOpts
        oopts.showXCanvas = False
        oopts.showYCanvas = False

        # Toggle off the cursor
        oopts.showCursor = False

        # Toggle off the radiological orientation
        self.displayCtx.radioOrientation = False

        # Invert the Y display
        self.frame.viewPanels[0].frame.viewPanels[0].getZCanvas().opts.invertY = True

        # Create a temporary directory that will hold the NIfTI files
        self.ads_temp_dir_var = tempfile.TemporaryDirectory()  #This variable needs to stay loaded to keep the temporary
                                                               # directory from being destroyed
        self.ads_temp_dir = Path(self.ads_temp_dir_var.name)

        # Check the version
        self.verrify_version()


    def on_load_png_button(self, event):
        """
        This function is called when the user presses on the Load Png button. It allows the user to select a PNG or TIF
        image, convert it into a NIfTI and load it into FSLeyes.
        """
        # Ask the user which file he wants to convert
        with wx.FileDialog(
            self, "select Image file", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:

            if (
                file_dialog.ShowModal() == wx.ID_CANCEL
            ):  # The user cancelled the operation
                return

            in_file = Path(file_dialog.GetPath())

        # Check if the image format is valid
        image_extension = in_file.suffix
        valid_extensions = [".png", ".tif", ".jpg", ".jpeg"]
        if image_extension not in valid_extensions:
            self.show_message("Invalid file extension")
            return

        # Store the directory path and image name for later use in the application of the prediction model
        self.image_dir_path.append(in_file.parents[0])
        self.png_image_name.append(in_file.name)

        # Call the function that convert and loads the png or tif image
        self.load_png_image_from_path(in_file)

    def on_load_mask_button(self, event):
        """
        This function is called when the user presses on the loadMask button. It allows the user to select an existing
        PNG mask, convert it into a NIfTI and load it into FSLeyes.
        The mask needs to contain an axon + myelin mask. The Axons should have an intensity > 200. The myelin should
        have an intensity between 100 and 200. The data should be in uint8.
        """
        # Ask the user to select the mask image
        with wx.FileDialog(
            self, "select mask .png file", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:

            if (
                file_dialog.ShowModal() == wx.ID_CANCEL
            ):  # The user cancelled the operation
                return

            in_file = Path(file_dialog.GetPath())

        # Check if the image format is valid
        image_extension = in_file.suffix
        valid_extensions = [".png", ".tif", ".jpg", ".jpeg"]
        if image_extension not in valid_extensions:
            self.show_message("Invalid file extension")
            return

        # Get the image data
        img_png2D = ads_utils.imread(in_file)
        image_name = in_file.stem

        # Extract the Axon mask
        axon_mask = img_png2D > 200
        axon_mask = params.intensity['binary'] * np.array(axon_mask, dtype=np.uint8)

        # Extract the Myelin mask
        myelin_mask = (img_png2D > 100) & (img_png2D < 200)
        myelin_mask = params.intensity['binary'] * np.array(myelin_mask, dtype=np.uint8)

        # Load the masks into FSLeyes
        axon_outfile = self.ads_temp_dir / (image_name + "-axon.png")
        ads_utils.imwrite(axon_outfile, axon_mask)
        self.load_png_image_from_path(axon_outfile, is_mask=True, colormap="blue")

        myelin_outfile = self.ads_temp_dir / (image_name + "-myelin.png")
        ads_utils.imwrite(myelin_outfile, myelin_mask)
        self.load_png_image_from_path(myelin_outfile, is_mask=True, colormap="red")

    def on_apply_model_button(self, event):
        """
        This function is called when the user presses on the ApplyModel button. It is used to apply the prediction model
        selected in the combobox. The segmentation masks are then loaded into FSLeyes
        """

        # Declare the default resolution of the model
        resolution = 0.1

        # Get the image name and directory
        image_overlay = self.get_visible_image_overlay()
        if self.get_visible_image_overlay() is None:
            return

        n_loaded_images = self.png_image_name.__len__()
        image_name = None
        image_directory = None
        for i in range(n_loaded_images):
            if image_overlay.name == (Path(self.png_image_name[i])).stem:
                image_name = self.png_image_name[i]
                image_directory = self.image_dir_path[i]

        if (image_name is None) or (image_directory is None):
            self.show_message(
                "Couldn't find the path to the loaded image. "
                "Please use the plugin's image loader to import the image you wish to segment. "
            )
            return

        image_path = image_directory / image_name
        image_name_no_extension = Path(image_name).stem

        # Get the selected model
        selected_model = self.model_combobox.GetStringSelection()

        # Get the path of the selected model
        if any(selected_model in models for models in ads_utils.get_existing_models_list()):
            dir_path = Path(AxonDeepSeg.__file__).parents[0]
            model_path = dir_path / "models" / selected_model
        else:
            self.show_message("Please select a model")
            return

        # If the TEM model is selected, modify the resolution
        if "TEM" in selected_model.upper():
            resolution = 0.01

        # Check if the pixel size txt file exist in the imageDirPath
        pixel_size_exists = (image_directory / "pixel_size_in_micrometer.txt").exists()

        # if it doesn't exist, ask the user to input the pixel size
        if pixel_size_exists is False:
            with wx.TextEntryDialog(
                self, "Enter the pixel size in micrometer", value="0.07"
            ) as text_entry:
                if text_entry.ShowModal() == wx.ID_CANCEL:
                    return

                pixel_size_str = text_entry.GetValue()
            pixel_size_float = float(pixel_size_str)

        else:  # read the pixel size
            resolution_file = open((image_directory / "pixel_size_in_micrometer.txt").__str__(), 'r')
            pixel_size_float = float(resolution_file.read())


        # Load model configs and apply prediction
        model_configfile = model_path / "config_network.json"
        with open(model_configfile.__str__(), "r") as fd:
            config_network = json.loads(fd.read())

        segment_image(
                      image_path,
                      model_path,
                      25,
                      config_network,
                      resolution,
                      acquired_resolution=pixel_size_float,
                      verbosity_level=3
                      )

        # The axon_segmentation function creates the segmentation masks and stores them as PNG files in the same folder
        # as the original image file.

        # Load the axon and myelin masks into FSLeyes
        axon_mask_path = image_directory / (image_name_no_extension + str(axon_suffix))
        myelin_mask_path = image_directory / (image_name_no_extension + str(myelin_suffix))
        self.load_png_image_from_path(axon_mask_path, is_mask=True, colormap="blue")
        self.load_png_image_from_path(myelin_mask_path, is_mask=True, colormap="red")
        self.pixel_size_float = pixel_size_float

        return self

    def on_save_segmentation_button(self, event):
        """
        This function saves the active myelin and axon masks as PNG images. Three (3) images are generated in a folder
        selected by the user : one with the axon mask, one with the myelin mask and one with both.
        """

        # Find the visible myelin and axon masks
        axon_mask_overlay = self.get_corrected_axon_overlay()
        if axon_mask_overlay is None:
            axon_mask_overlay = self.get_visible_axon_overlay()
        myelin_mask_overlay = self.get_visible_myelin_overlay()

        if (axon_mask_overlay is None) or (myelin_mask_overlay is None):
            return

        # Ask the user where to save the segmentation
        with wx.DirDialog(
            self,
            "select the directory in which the segmentation will be save",
            defaultPath="",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        ) as file_dialog:

            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return

        save_dir = Path(file_dialog.GetPath())

        # store the data of the masks in variables as numpy arrays.
        # Note: since PIL uses a different convention for the X and Y coordinates, some array manipulation has to be
        # done.
        # Note 2 : The image array loaded in FSLeyes is flipped. We need to flip it back

        myelin_array = np.array(
            myelin_mask_overlay[:, :, 0], copy=True, dtype=np.uint8
        )
        myelin_array = np.flipud(myelin_array)
        myelin_array = np.rot90(myelin_array, k=1, axes=(1, 0))
        axon_array = np.array(
            axon_mask_overlay[:, :, 0], copy=True, dtype=np.uint8
        )
        axon_array = np.flipud(axon_array)
        axon_array = np.rot90(axon_array, k=1, axes=(1, 0))

        # Make sure the masks have the same size
        if myelin_array.shape != axon_array.shape:
            self.show_message("invalid visible masks dimensions")
            return

        # Remove the intersection
        myelin_array, axon_array, intersection = postprocessing.remove_intersection(
            myelin_array, axon_array, priority=1, return_overlap=True)

        if intersection.sum() > 0:
            self.show_message(
                "There is an overlap between the axon mask and the myelin mask. The myelin will have priority.")

        # Scale the pixel values of the masks to 255 for image saving
        myelin_array = myelin_array * params.intensity['binary']
        axon_array = axon_array * params.intensity['binary']

        image_name = myelin_mask_overlay.name[:-len("_seg-myelin")]

        myelin_and_axon_array = (myelin_array // 2 + axon_array).astype(np.uint8)

        ads_utils.imwrite(filename=save_dir / (image_name + str(axonmyelin_suffix)), img=myelin_and_axon_array)
        ads_utils.imwrite(filename=save_dir / (image_name + str(myelin_suffix)), img=myelin_array)
        ads_utils.imwrite(filename=save_dir / (image_name + str(axon_suffix)), img=axon_array)

    def on_run_watershed_button(self, event):
        """
        This function is called then the user presses on the runWatershed button. This creates a watershed mask that is
        used to locate where are the connections between the axon-myelin objects.
        The runWatershed button is currently commented, so this function is unused at the moment.
        """

        # Find the visible myelin and axon masks
        axon_mask_overlay = self.get_visible_axon_overlay()
        myelin_mask_overlay = self.get_visible_myelin_overlay()

        if (axon_mask_overlay is None) or (myelin_mask_overlay is None):
            return

        # Extract the data from the overlays
        axon_array = axon_mask_overlay[:, :, 0]
        myelin_array = myelin_mask_overlay[:, :, 0]

        # Make sure the masks have the same size
        if myelin_array.shape != axon_array.shape:
            self.show_message("invalid visible masks dimensions")
            return

        # If a watershed mask already exists, remove it.
        for an_overlay in self.overlayList:
            if (self.most_recent_watershed_mask_name is not None) and (
                an_overlay.name == self.most_recent_watershed_mask_name
            ):
                self.overlayList.remove(an_overlay)

        # Compute the watershed mask
        watershed_data = self.get_watershed_segmentation(axon_array, myelin_array)

        # Save the watershed mask as a png then load it as an overlay
        watershed_image_array = np.rot90(watershed_data, k=3, axes=(1, 0))
        watershed_image = Image.fromarray(watershed_image_array)
        file_name = self.ads_temp_dir.name + "/watershed_mask.png"
        watershed_image.save(file_name)
        wantershed_mask_overlay = self.load_png_image_from_path(
            file_name, add_to_overlayList=False
        )
        wantershed_mask_overlay[:, :, 0] = watershed_data
        self.overlayList.append(wantershed_mask_overlay)

        # Apply a "random" colour mapping to the watershed mask
        opts = self.displayCtx.getOpts(wantershed_mask_overlay)
        opts.cmap = "random"

        self.most_recent_watershed_mask_name = "watershed_mask"

    def on_fill_axons_button(self, event):
        """
        This function is called when the fillAxon button is pressed by the user. It uses a flood fill algorithm to fill
        the inside of the myelin objects with the axon mask
        """
        # Find the visible myelin and axon mask
        myelin_mask_overlay = self.get_visible_myelin_overlay()

        if myelin_mask_overlay is None:
            return

        # Extract the data from the overlays
        myelin_array = myelin_mask_overlay[:, :, 0]

        # Perform the floodfill operation
        axon_extracted_array = postprocessing.fill_myelin_holes(myelin_array)

        axon_corr_array = np.flipud(axon_extracted_array)
        axon_corr_array = params.intensity['binary'] * np.rot90(axon_corr_array, k=1, axes=(1, 0))
        file_name = self.ads_temp_dir / (myelin_mask_overlay.name[:-len("-myelin")] + "-axon-corr.png")
        ads_utils.imwrite(filename=file_name, img=axon_corr_array)
        self.load_png_image_from_path(file_name, is_mask=True, colormap="blue")

    def on_compute_morphometrics_button(self, event):
        """
        Compute morphometrics and save them to an Excel file.
        """

        # Get pixel size

        try:
            pixel_size = self.pixel_size_float
        except:
            with wx.TextEntryDialog(
                self, "Enter the pixel size in micrometer", value="0.07"
            ) as text_entry:
                if text_entry.ShowModal() == wx.ID_CANCEL:
                    return

                pixel_size_str = text_entry.GetValue()
            pixel_size = float(pixel_size_str)

        # Find the visible myelin and axon masks
        axon_mask_overlay = self.get_corrected_axon_overlay()
        if axon_mask_overlay is None:
            axon_mask_overlay = self.get_visible_axon_overlay()
        myelin_mask_overlay = self.get_visible_myelin_overlay()

        if (axon_mask_overlay is None) or (myelin_mask_overlay is None):
            return

        # store the data of the masks in variables as numpy arrays.
        # Note: since PIL uses a different convention for the X and Y coordinates, some array manipulation has to be
        # done.
        # Note 2 : The image array loaded in FSLeyes is flipped. We need to flip it back

        myelin_array = np.array(
            myelin_mask_overlay[:, :, 0] * params.intensity['binary'], copy=True, dtype=np.uint8
        )
        myelin_array = np.flipud(myelin_array)
        myelin_array = np.rot90(myelin_array, k=1, axes=(1, 0))
        axon_array = np.array(
            axon_mask_overlay[:, :, 0] * params.intensity['binary'], copy=True, dtype=np.uint8
        )
        axon_array = np.flipud(axon_array)
        axon_array = np.rot90(axon_array, k=1, axes=(1, 0))

        # Make sure the masks have the same size
        if myelin_array.shape != axon_array.shape:
            self.show_message("invalid visible masks dimensions")
            return

        # Save the arrays as PNG files
        pred = (myelin_array // 2 + axon_array).astype(np.uint8)

        pred_axon = pred > 200
        pred_myelin = np.logical_and(pred >= 50, pred <= 200)

        x = np.array([], dtype=[
                                ('x0', 'f4'),
                                ('y0', 'f4'),
                                ('gratio','f4'),
                                ('axon_area','f4'),
                                ('myelin_area','f4'),
                                ('axon_diam','f4'),
                                ('myelin_thickness','f4'),
                                ('axonmyelin_area','f4'),
                                ('solidity','f4'),
                                ('eccentricity','f4'),
                                ('orientation','f4')
                            ]
                    )

        # Compute statistics
        stats_array = get_axon_morphometrics(im_axon=pred_axon, im_myelin=pred_myelin, pixel_size=pixel_size)

        for stats in stats_array:

            x = np.append(x,
                np.array(
                    [(
                    stats['x0'],
                    stats['y0'],
                    stats['gratio'],
                    stats['axon_area'],
                    stats['myelin_area'],
                    stats['axon_diam'],
                    stats['myelin_thickness'],
                    stats['axonmyelin_area'],
                    stats['solidity'],
                    stats['eccentricity'],
                    stats['orientation']
                    )],
                    dtype=x.dtype)
                )

        with wx.FileDialog(self, "Save morphometrics file", wildcard="Excel files (*.xlsx)|*.xlsx",
                       style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            # save the current contents in the file
            pathname = fileDialog.GetPath()
            if not (pathname.lower().endswith((".xlsx", ".csv"))):  # If the user didn't add the extension, add it here
                pathname = pathname + ".xlsx"
            try:
                # Export to excel
                pd.DataFrame(x).to_excel(pathname)

            except IOError:
                wx.LogError("Cannot save current data in file '%s'." % pathname)

        # Create the axon coordinate array
        mean_diameter_in_pixel = np.average(x['axon_diam']) / pixel_size
        axon_indexes = np.arange(x.size)
        number_array = postprocessing.generate_axon_numbers_image(axon_indexes, x['x0'], x['y0'],
                                                                  tuple(reversed(axon_array.shape)),
                                                                  mean_diameter_in_pixel)

        # Load the axon coordinate image into FSLeyes
        number_outfile = self.ads_temp_dir / "numbers.png"
        ads_utils.imwrite(number_outfile, number_array)
        self.load_png_image_from_path(number_outfile, is_mask=False, colormap="yellow")

        return

    def get_watershed_segmentation(self, im_axon, im_myelin, return_centroids=False):
        """
        Parts of this function were copied from the code found in this document :
        https://github.com/neuropoly/axondeepseg/blob/master/AxonDeepSeg/morphometrics/compute_morphometrics.py
        In the future, the referenced script should be modified in order to avoid repetition.
        :param im_axon: the binary mask corresponding to axons
        :type im_axon: ndarray
        :param im_myelin: the binary mask corresponding to the myelin
        :type im_myelin: ndarray
        :param return_centroids: (optional) if this is set to true, the function will also return the centroids of the
        axon objects as a list of tuples
        :type return_centroids: bool
        :return: the label corresponding to the axon+myelin objects
        :rtype: ndarray
        """

        # Label each axon object
        im_axon_label = measure.label(im_axon)
        # Measure properties for each axon object
        axon_objects = measure.regionprops(im_axon_label)
        # Deal with myelin mask
        if im_myelin is not None:
            # sum axon and myelin masks
            im_axonmyelin = im_axon + im_myelin
            # Compute distance between each pixel and the background. Note: this distance is calculated from the im_axon,
            # note from the im_axonmyelin image, because we know that each axon object is already isolated, therefore the
            # distance metric will be more useful for the watershed algorithm below.
            distance = ndi.distance_transform_edt(im_axon)
            # local_maxi = feature.peak_local_max(distance, indices=False, footprint=np.ones((31, 31)), labels=axonmyelin)

            # Get axon centroid as int (not float) to be used as index
            ind_centroid = (
                [int(props.centroid[0]) for props in axon_objects],
                [int(props.centroid[1]) for props in axon_objects],
            )

            # Create an image with axon centroids, which value corresponds to the value of the axon object
            im_centroid = np.zeros_like(im_axon, dtype="uint16")
            for i in range(len(ind_centroid[0])):
                # Note: The value "i" corresponds to the label number of im_axon_label
                im_centroid[ind_centroid[0][i], ind_centroid[1][i]] = i + 1

            # Watershed segmentation of axonmyelin using distance map
            im_axonmyelin_label = morphology.watershed(
                -distance, im_centroid, mask=im_axonmyelin
            )
            if return_centroids is True:
                return im_axonmyelin_label, ind_centroid
            else:
                return im_axonmyelin_label

    def load_png_image_from_path(
        self, image_path, is_mask=False, add_to_overlayList=True, colormap="greyscale"
    ):
        """
        This function converts a 2D image into a NIfTI image and loads it as an overlay.
        The parameter add_to_overlayList allows to display the overlay into FSLeyes.
        :param image_path: The location of the image, including the name and the .extension
        :type image_path: Path
        :param is_mask: (optional) Whether or not this is a segmentation mask. It will be treated as a normal
        image by default.
        :type is_mask: bool
        :param add_to_overlayList: (optional) Whether or not to add the image to the overlay list. If so, the image will
        be displayed in the application. This parameter is True by default.
        :type add_to_overlayList: bool
        :param colormap: (optional) the colormap of image that will be displayed. This parameter is set to greyscale by
        default.
        :type colormap: string
        :return: the FSLeyes overlay corresponding to the loaded image.
        :rtype: overlay
        """

        # Open the 2D image
        img_png2D = ads_utils.imread(image_path)

        if is_mask is True:
            img_png2D = img_png2D // params.intensity['binary']  # Segmentation masks should be binary

        # Flip the image on the Y axis so that the morphometrics file shows the right coordinates
        img_png2D = np.flipud(img_png2D)

        # Convert image data into a NIfTI image
        # Note: PIL and NiBabel use different axis conventions, so some array manipulation has to be done.
        img_NIfTI = nib.Nifti1Image(
            np.rot90(img_png2D, k=1, axes=(1, 0)), np.eye(4)
        )

        # Save the NIfTI image in a temporary directory
        img_name = image_path.stem
        out_file = self.ads_temp_dir.__str__() + "/" + img_name + ".nii.gz"
        nib.save(img_NIfTI, out_file)

        # Load the NIfTI image as an overlay
        img_overlay = ovLoad.loadOverlays(paths=[out_file], inmem=True, blocking=True)[
            0
        ]

        # Display the overlay
        if add_to_overlayList is True:
            self.overlayList.append(img_overlay)
            opts = self.displayCtx.getOpts(img_overlay)
            opts.cmap = colormap

        return img_overlay

    def get_visible_overlays(self):
        """
        This function returns a list containing evey overlays that are visible on FSLeyes.
        :return: The list of the visible overlays
        :rtype: list
        """

        visible_overlay_list = []
        for an_overlay in self.overlayList:
            an_overlay_display = self.displayCtx.getDisplay(an_overlay)
            if an_overlay_display.enabled is True:
                visible_overlay_list.append(an_overlay)

        return visible_overlay_list

    def get_visible_image_overlay(self):
        """
        This function is used to find the active microscopy image. This image should be visible and should NOT have the
        following keywords in its name : axon, myelin, Myelin, watershed, Watershed.
        :return: The visible microscopy image
        :rtype: overlay
        """
        visible_overlay_list = self.get_visible_overlays()
        image_overlay = None
        n_found_overlays = 0

        if visible_overlay_list.__len__() is 0:
            self.show_message("No overlays are displayed")
            return None

        if visible_overlay_list.__len__() is 1:
            return visible_overlay_list[0]

        for an_overlay in visible_overlay_list:
            if (
                ("watershed" not in an_overlay.name)
                and ("Watershed" not in an_overlay.name)
                and (not an_overlay.name.endswith("-myelin"))
                and (not an_overlay.name.endswith("-Myelin"))
                and (not an_overlay.name.endswith("-Axon"))
                and (not an_overlay.name.endswith("-axon"))
            ):
                n_found_overlays = n_found_overlays + 1
                image_overlay = an_overlay

        if n_found_overlays > 1:
            self.show_message("More than one microscopy image has been found")
            return None
        if n_found_overlays is 0:
            self.show_message("No visible microscopy image has been found")
            return None

        return image_overlay

    def get_visible_axon_overlay(self):
        """
        This method finds the currently visible axon overlay
        :return: The visible overlay that corresponds to the axon mask
        :rtype: overlay
        """
        visible_overlay_list = self.get_visible_overlays()
        axon_overlay = None
        n_found_overlays = 0

        if visible_overlay_list.__len__() is 0:
            self.show_message("No overlays are displayed")
            return None

        for an_overlay in visible_overlay_list:
            if (an_overlay.name.endswith("-axon")) or (an_overlay.name.endswith("-Axon")):
                n_found_overlays = n_found_overlays + 1
                axon_overlay = an_overlay

        if n_found_overlays > 1:
            self.show_message("More than one axon mask has been found")
            return None
        if n_found_overlays is 0:
            self.show_message("No visible axon mask has been found")
            return None

        return axon_overlay

    def get_corrected_axon_overlay(self):
        """
        This method finds a the visible corrected axon overlay if it exists
        :return: The visible corrected axon overlay
        :rtype overlay
        """
        visible_overlay_list = self.get_visible_overlays()
        axon_overlay = None
        n_found_overlays = 0

        if visible_overlay_list.__len__() is 0:
            self.show_message("No overlays are displayed")
            return None

        for an_overlay in visible_overlay_list:
            if (an_overlay.name.endswith("-axon-corr")) or (an_overlay.name.endswith("-Axon-corr")):
                n_found_overlays = n_found_overlays + 1
                axon_overlay = an_overlay

        if n_found_overlays > 1:
            self.show_message("More than one corrected axon mask has been found")
            return None
        if n_found_overlays is 0:
            return None

        return axon_overlay

    def get_visible_myelin_overlay(self):
        """
        This method finds the currently visible myelin overlay
        :return: The visible overlay that corresponds to the myelin mask
        :rtype: overlay
        """
        visible_overlay_list = self.get_visible_overlays()
        myelin_overlay = None
        n_found_overlays = 0

        if visible_overlay_list.__len__() is 0:
            self.show_message("No overlays are displayed")
            return None

        for an_overlay in visible_overlay_list:
            if (an_overlay.name.endswith("-myelin")) or (an_overlay.name.endswith("-Myelin")):
                n_found_overlays = n_found_overlays + 1
                myelin_overlay = an_overlay

        if n_found_overlays > 1:
            self.show_message("More than one myelin mask has been found")
            return None
        if n_found_overlays is 0:
            self.show_message("No visible myelin mask has been found")
            return None

        return myelin_overlay

    def show_message(self, message, caption="Error"):
        """
        This function is used to show a popup message on the FSLeyes interface.
        :param message: The message to be displayed.
        :type message: String
        :param caption: (Optional) The caption of the message box.
        :type caption: String
        """
        with wx.MessageDialog(
            self,
            message,
            caption=caption,
            style=wx.OK | wx.CENTRE,
            pos=wx.DefaultPosition,
        ) as msg:
            msg.ShowModal()

    def verrify_version(self):
        """
        This function checks if the plugin version is the same as the one in the AxonDeepSeg directory
        """
        ads_path = Path(AxonDeepSeg.__file__).parents[0]
        plugin_path_parts = ads_path.parts[:-1]
        plugin_path = Path(*plugin_path_parts)
        plugin_file = plugin_path / "ads_plugin.py"

        # Check if the plugin file exists
        plugin_file_exists = plugin_file.exists()

        if plugin_file_exists is False:
            return

        # Check the version of the plugin
        with open(plugin_file.__str__()) as plugin_file_reader:
            plugin_file_lines = plugin_file_reader.readlines()

        plugin_file_lines = [x.strip() for x in plugin_file_lines]
        version_line = 'VERSION = "' + VERSION + '"'
        plugin_is_up_to_date = True
        version_found = False

        for lines in plugin_file_lines:
            if (lines.startswith("VERSION = ")):
                version_found = True
                if not (lines == version_line):
                    plugin_is_up_to_date = False

        if (version_found is False) or (plugin_is_up_to_date is False):
            message = (
                "A more recent version of the AxonDeepSeg plugin was found in your AxonDeepSeg installation folder. "
                "You will need to replace the current FSLeyes plugin which the new one. "
                "To proceed, go to: file -> load plugin -> ads_plugin.py. Then, restart FSLeyes."
            )
            self.show_message(message, "Warning")
        return

    def get_citation(self):
        """
        This function returns the AxonDeepSeg paper citation.
        :return: The AxonDeepSeg citation
        :rtype: string
        """

        return (
            "If you use this work in your research, please cite it as follows: \n"
            "Zaimi, A., Wabartha, M., Herman, V., Antonsanti, P.-L., Perone, C. S., & Cohen-Adad, J. (2018). "
            "AxonDeepSeg: automatic axon and myelin segmentation from microscopy data using convolutional "
            "neural networks. Scientific Reports, 8(1), 3816. "
            "Link to paper: https://doi.org/10.1038/s41598-018-22181-4. \n"
            "Copyright (c) 2018 NeuroPoly (Polytechnique Montreal)"
        )

    def get_logo(self):
        """
        This function finds the AxonDeepSeg logo saved as a png image and returns it as a wx bitmap image.
        :return: The AxonDeepSeg logo
        :rtype: wx.StaticBitmap
        """

        ads_path = Path(AxonDeepSeg.__file__).parents[0]

        logo_file = ads_path / "logo_ads-alpha_small.png"

        png = wx.Image(str(logo_file), wx.BITMAP_TYPE_ANY).ConvertToBitmap()
        png.SetSize((png.GetWidth(), png.GetHeight()))
        logo_image = wx.StaticBitmap(
            self, -1, png, wx.DefaultPosition, (png.GetWidth(), png.GetHeight())
        )
        return logo_image

    @staticmethod
    def supportedViews():
        """
        I am not sure what this method does.
        """
        from fsleyes.views.orthopanel import OrthoPanel

        return [OrthoPanel]

    @staticmethod
    def defaultLayout():
        """
        This method makes the control panel appear on the left of the FSLeyes window.
        """
        return {"location": wx.LEFT}

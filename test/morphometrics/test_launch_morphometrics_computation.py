# coding: utf-8

from pathlib import Path
import random
import string
import pytest

from AxonDeepSeg.morphometrics.launch_morphometrics_computation import *
from config import axonmyelin_suffix


class TestCore(object):
    def setup(self):
        # Get the directory where this current file is saved
        self.fullPath = Path(__file__).resolve().parent
        # Move up to the test directory, "test/"
        self.testPath = self.fullPath.parent
        self.dataPath = self.testPath / '__test_files__' / '__test_demo_files__'

        self.axon_shape = "ellipse"         # axon shape is set to ellipse

    def teardown(self):
        pass

    # --------------launch_morphometrics_computation tests-------------- #
    @pytest.mark.unit
    def test_launch_morphometrics_computation_saves_expected_files(self):
        expectedFiles = {'aggregate_morphometrics.txt',
                         'AxonDeepSeg_map-axondiameter.png',
                         'axonlist.npy'
                         }

        pathImg = self.dataPath / 'image.png'
        pathPrediction = self.dataPath / ('image' + str(axonmyelin_suffix))

        launch_morphometrics_computation(str(pathImg), str(pathPrediction))

        for fileName in expectedFiles:
            fullFilePath = self.dataPath / fileName
            assert fullFilePath.is_file()
            fullFilePath.unlink()

    @pytest.mark.unit
    def test_launch_morphometrics_computation_saves_expected_files_with_axon_as_ellipse(self):
        expectedFiles = {'aggregate_morphometrics.txt',
                         'AxonDeepSeg_map-axondiameter.png',
                         'axonlist.npy'
                         }

        pathImg = self.dataPath / 'image.png'
        pathPrediction = self.dataPath / ('image' + str(axonmyelin_suffix))

        launch_morphometrics_computation(str(pathImg), str(pathPrediction), axon_shape=self.axon_shape)

        for fileName in expectedFiles:
            fullFilePath = self.dataPath / fileName
            assert fullFilePath.is_file()
            fullFilePath.unlink()

    @pytest.mark.unit
    def test_launch_morphometrics_computation_errors_for_missing_file(self):
        nonExistingFile = ''.join(random.choice(string.ascii_lowercase) for i in range(16))
        pathPrediction = self.dataPath / ('image' + str(axonmyelin_suffix))

        with pytest.raises((IOError, OSError)):
            launch_morphometrics_computation(str(nonExistingFile), str(pathPrediction))

# coding: utf-8

import pytest
from pathlib import Path
import numpy as np

from AxonDeepSeg import ads_utils
from AxonDeepSeg import postprocessing


class TestCore(object):
    def setup(self):
        # Get the directory where this current file is saved
        self.fullPath = Path(__file__).resolve().parent

        self.test_files_path = (self.fullPath / '__test_files__' / '__test_postprocessing_files__')
        print(self.test_files_path)

        self.before_floodfill_image = ads_utils.imread((self.test_files_path / 'before_flood_fill.png'))
        self.after_floodfill_image = ads_utils.imread((self.test_files_path / 'after_flood_fill.png'))

    def teardown(self):
        pass

    @pytest.mark.unit
    def test_get_centroids_returns_expected_list(self):
        axon_mask, _ = ads_utils.extract_axon_and_myelin_masks_from_image_data(self.before_floodfill_image)
        expected_centroids = ([5, 11, 41, 55], [5, 53, 39, 53])
        obtained_centroids = postprocessing.get_centroids(axon_mask)
        assert sorted(expected_centroids) == sorted(obtained_centroids)

    @pytest.mark.unit
    def test_floodfill_axons_returns_expected_arrays(self):
        before_ff_axon_mask, before_ff_myelin_mask = \
            ads_utils.extract_axon_and_myelin_masks_from_image_data(self.before_floodfill_image)
        after_ff_expected_axon_mask, _ = \
            ads_utils.extract_axon_and_myelin_masks_from_image_data(self.after_floodfill_image)
        after_ff_obtained_axon_mask = postprocessing.floodfill_axons(before_ff_myelin_mask)

        assert np.array_equal(after_ff_obtained_axon_mask, after_ff_expected_axon_mask)

    @pytest.mark.unit
    def test_remove_intersection_returns_expected_arrays(self):
        mask1_in = np.zeros((3, 3))
        mask1_in[:, 0:2] = 1

        mask2_in = np.zeros((3, 3))
        mask2_in[:, 1:3] = 1

        mask1_expected_out = np.zeros((3, 3))
        mask1_expected_out[:, 0] = 1

        mask2_expected_out = np.array(mask2_in, copy=True)

        expected_overlap = np.zeros((3, 3))
        expected_overlap[:, 1] = 1

        mask1_obtained_out, mask2_obtained_out, obtained_overlap = \
            postprocessing.remove_intersection(mask1_in, mask2_in, priority=2, return_overlap=True)

        expectations = [mask1_expected_out, mask2_expected_out, expected_overlap]
        obtained_results = [mask1_expected_out, mask2_expected_out, obtained_overlap]

        for i in range(expectations.__len__()):
            assert np.array_equal(expectations[i], obtained_results[i])

    @pytest.mark.unit
    def test_generate_axon_numbers_image_returns_expected_array(self):
        # Load the test image
        expected_image = ads_utils.imread((self.test_files_path / 'test_numbers_image.png'))
        expected_image = np.array(expected_image)

        # Atempt to recreate the test image
        obtained_image = postprocessing.generate_axon_numbers_image(
            centroid_index=np.array([0]),
            x0_array=[20],
            y0_array=[10],
            image_size=(30, 30),
            mean_axon_diameter_in_pixels=6
        )
        assert np.array_equal(expected_image, obtained_image)

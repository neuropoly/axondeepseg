# -*- coding: utf-8 -*-

from pathlib import Path
import os

# AxonDeepSeg imports
from AxonDeepSeg.network_construction import uconv_net
from AxonDeepSeg.data_management.input_data import DataGen
from AxonDeepSeg.ads_utils import convert_path
from AxonDeepSeg.config_tools import generate_config
import AxonDeepSeg.ads_utils

# Keras imports
import keras
from keras.models import load_model
from keras.callbacks import ModelCheckpoint, TensorBoard
import keras.backend.tensorflow_backend as K

K.set_session
import tensorflow as tf
from albumentations import (
                                Compose, 
                                Flip,
                                ShiftScaleRotate,
                                ElasticTransform,
                                GaussianBlur,
                                Rotate
                            )
import random
import cv2


def train_model(
    path_trainingset,
    path_model,
    config,
    path_model_init=None,
    save_trainable=True,
    gpu=None,
    debug_mode=False,
    gpu_per=1.0,
):
    """
    Main function. Trains a model using the configuration parameters.
    :param path_trainingset: Path to access the trainingset.
    :param path_model: Path indicating where to save the model.
    :param config: Dict, containing the configuration parameters of the network.
    :param path_model_init: Path to where the model to use for initialization is stored.
    :param save_trainable: Boolean. If True, only saves in the model variables that are trainable (evolve from gradient)
    :param gpu: String, name of the gpu to use. Prefer use of CUDA_VISIBLE_DEVICES environment variable.
    :param debug_mode: Boolean. If activated, saves more information about the distributions of
    most trainable variables, and also outputs more information.
    :param gpu_per: Float, between 0 and 1. Percentage of GPU to use.
    :return: Nothing.
    """

    # If string, convert to Path objects
    path_trainingset = convert_path(path_trainingset)
    path_model = convert_path(path_model)

    ###################################################################################################################
    ############################################## VARIABLES INITIALIZATION ###########################################
    ###################################################################################################################

    # Results and Models
    if not path_model.exists():
        path_model.mkdir(parents=True)

    # Translating useful variables from the config file.
    learning_rate = config["learning_rate"]
    batch_size = config["batch_size"]
    epochs = config["epochs"]
    image_size = config["trainingset_patchsize"]
    thresh_indices = config["thresholds"]
    if "checkpoint" in config:
        checkpoint = config["checkpoint"]
    else:
        # For retrocompatibility with old configs
        checkpoint = None
    if "checkpoint_period" in config:
        checkpoint_period = config["checkpoint_period"]
    else:
        # For retrocompatibility with old configs
        checkpoint_period = 5

    # Training and Validation Path

    path_training_set = path_trainingset / "Train"
    path_validation_set = path_trainingset / "Validation"

    # List of Training Ids
    no_train_images = int(len(os.listdir(path_training_set)) / 2)
    train_ids = [str(i) for i in range(no_train_images)]

    # List of Validation Ids
    no_valid_images = int(len(os.listdir(path_validation_set)) / 2)
    valid_ids = [str(i) for i in range(no_valid_images)]

    ###################################################################################################################
    ############################################# DATA AUGMENTATION ##################################################
    ###################################################################################################################

    shifting = (config["da-0-shifting-activate"],)
    rescaling = config["da-1-rescaling-activate"]
    rotation = config["da-2-random_rotation-activate"]
    elastic = config["da-3-elastic-activate"]
    flipping = config["da-4-flipping-activate"]
    gaussian_blur = False   # Gaussian Blur preserved for retrocompatibility with old configs
    if "da-5-gaussian_blur-activate" in config:
        gaussian_blur = config["da-5-gaussian_blur-activate"]
    elif "da-5-noise_addition-activate" in config:
        gaussian_blur = config["da-5-noise_addition-activate"]
    reflection_border = config[
        "da-6-reflection_border-activate"
    ]  # Config parameter to determine whether relection or constant(value = 0) is used for border pixel values while performing augmentation operations such as rotation, rescaling and shifting.

    if reflection_border:
        border_mode = cv2.BORDER_REFLECT_101
    else:
        border_mode = cv2.BORDER_CONSTANT

    p_shift = p_rescale = p_rotate = p_elastic = p_flip = p_blur = 0
    # If the key values of augmentation are set to True then their respective probability are set to 0.5 else to 0. Probalility(p) suggests a certainity of applying data augmentation operations (shift, rotate, blur, elastic, flip) to an image.

    # Probability value of 0.5 is chosen so that the original as well augmented image are taken into account while training the model.
    if shifting:
        p_shift = 0.5
    if rescaling:
        p_rescale = 0.5
    if rotation:
        p_rotate = 0.5
    if elastic:
        p_elastic = 0.5
    if flipping:
        p_flip = 0.5
    if gaussian_blur:
        p_blur = 0.5

    #####Data Augmentation parameters#####

    # Shifting parameters
    percentage_max = 0.1
    size_shift = int(percentage_max * image_size)
    low_limit = 0
    high_limit = (2 * size_shift - 1) / image_size

    # Rescaling parameters
    low_rescale_bound = 0.8
    high_rescale_bound = 1.2

    # Random rotation parameters
    low_bound = 5
    high_bound = 89

    # Elastic transform parameters
    alpha_max = 9
    sigma = 3
    alpha = random.choice(list(range(1, alpha_max)))

    ######################################

    AUGMENTATIONS_TRAIN = Compose(
        [
            # Randomly shifts an image between low limit and high limit.
            ShiftScaleRotate(
                shift_limit=(low_limit, high_limit),
                scale_limit=(0, 0),
                rotate_limit=(0, 0),
                border_mode=border_mode,
                p=p_shift,
                interpolation=cv2.INTER_NEAREST,
            ),
            # Randomly rescales an image between low rescale bound and high rescale bound.
            ShiftScaleRotate(
                shift_limit=(0, 0),
                scale_limit=(low_rescale_bound, high_rescale_bound),
                rotate_limit=(0, 0),
                border_mode=border_mode,
                p=p_shift,
                interpolation=cv2.INTER_NEAREST,
            ),
            # Randomly rotates the image between low bound and high bound.
            Rotate(
                limit=(low_bound, high_bound),
                border_mode=border_mode,
                p=p_rotate,
                interpolation=cv2.INTER_NEAREST,
            ),
            # Randomly applies elastic transformation on the image.
            ElasticTransform(
                alpha=alpha,
                sigma=sigma,
                p=p_elastic,
                alpha_affine=alpha,
                interpolation=cv2.INTER_NEAREST,
            ),
            # Randomy flips an image either horizontally, vertically or both.
            Flip(p=p_flip),
            # Blurs an image using gaussian kernel.
            GaussianBlur(p=p_blur),
        ]
    )

    AUGMENTATIONS_TEST = Compose([])

    ###################################################################################################################

    # Loading the Training images and masks in batch
    train_generator = DataGen(
        train_ids,
        path_training_set,
        batch_size=batch_size,
        image_size=image_size,
        thresh_indices=thresh_indices,
        augmentations=AUGMENTATIONS_TRAIN,
    )

    # Loading the Validation images and masks in batch
    valid_generator = DataGen(
        valid_ids,
        path_validation_set,
        batch_size=batch_size,
        image_size=image_size,
        thresh_indices=thresh_indices,
        augmentations=AUGMENTATIONS_TEST,
    )

    ########################### Initalizing U-Net Model ###########

    model = uconv_net(config, bn_updated_decay=None, verbose=True)

    ########################### Tensorboard for Visualization ###########
    tensorboard = TensorBoard(log_dir=str(path_model))

    ########################## Training Unet Model ###########

    # Adam Optimizer for Unet
    adam = keras.optimizers.Adam(
        lr=learning_rate, beta_1=0.9, beta_2=0.999, epsilon=1e-08, decay=0.0
    )

    # Compile the model with Categorical Cross Entropy loss and Adam Optimizer
    model.compile(
        optimizer=adam,
        loss=dice_coef_loss,
        metrics=["accuracy", dice_axon, dice_myelin],
    )

    train_steps = len(train_ids) // batch_size
    valid_steps = len(valid_ids) // batch_size

    ########################## Use Checkpoints to save best Accuracy and Loss ###########

    # Save the checkpoint in the /models/path_model folder
    filepath_acc = str(path_model) + "/best_acc_model.ckpt"

    # Keep only a single checkpoint, the best over test accuracy.
    checkpoint_acc = ModelCheckpoint(
        filepath_acc,
        monitor="val_acc",
        verbose=0,
        save_best_only=True,
        mode="max",
        period=checkpoint_period,
    )

    # Save the checkpoint in the /models/path_model folder
    filepath_loss = str(path_model) + "/best_loss_model.ckpt"

    # Keep only a single checkpoint, the best over test loss.
    checkpoint_loss = ModelCheckpoint(
        filepath_loss,
        monitor="val_loss",
        verbose=0,
        save_best_only=True,
        mode="min",
        period=checkpoint_period,
    )

    ########################## Training ###########
    
    if checkpoint == "loss":
        model.load_weights(filepath_loss)
    elif checkpoint == "accuracy":
        model.load_weights(filepath_acc)

    model.fit_generator(
        train_generator,
        validation_data=(valid_generator),
        steps_per_epoch=train_steps,
        validation_steps=valid_steps,
        epochs=epochs,
        callbacks=[tensorboard, checkpoint_loss, checkpoint_acc],
    )

    ########################## Save the model after Training ###########

    model.save(str(path_model / "model.hdf5"))

    # Add ops to save and restore all the variables.
    saver = tf.train.Saver()

    # Save Model in ckpt format
    custom_objects = {
        "dice_axon": dice_axon,
        "dice_myelin": dice_myelin,
        "dice_coef_loss": dice_coef_loss,
    }
    model = load_model(
        str(path_model) + "/model.hdf5", custom_objects=custom_objects
    )

    sess = K.get_session()
    # Save the model to be used by TF framework
    save_path = saver.save(sess, str(path_model) + "/model.ckpt")


# Defining the Loss and  Performance Metrics


def dice_myelin(y_true, y_pred, smooth=1e-3):
    """
    Computes the pixel-wise dice myelin coefficient from the prediction tensor outputted by the network.
    :param y_pred: Tensor, the prediction outputted by the network. Shape (N,H,W,C).
    :param y_true: Tensor, the gold standard we work with. Shape (N,H,W,C).
    :return:  dice myelin coefficient for the current batch.
    """

    y_true_f = K.flatten(y_true[..., 1])
    y_pred_f = K.flatten(y_pred[..., 1])
    intersection = K.sum(y_true_f * y_pred_f)
    return K.mean(
        (2.0 * intersection + smooth)
        / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)
    )


def dice_axon(y_true, y_pred, smooth=1e-3):
    """
    Computes the pixel-wise dice myelin coefficient from the prediction tensor outputted by the network.
    :param y_pred: Tensor, the prediction outputed by the network. Shape (N,H,W,C).
    :param y_true: Tensor, the gold standard we work with. Shape (N,H,W,C).
    :return: dice axon coefficient for the current batch.
    """

    y_true_f = K.flatten(y_true[..., 2])
    y_pred_f = K.flatten(y_pred[..., 2])
    intersection = K.sum(y_true_f * y_pred_f)
    return K.mean(
        (2.0 * intersection + smooth)
        / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)
    )


def dice_coef(y_true, y_pred, smooth=1e-3):
    y_true_f = K.flatten(y_true)
    y_pred_f = K.flatten(y_pred)
    intersection = K.sum(y_true_f * y_pred_f)
    return K.mean(
        (2.0 * intersection + smooth)
        / (K.sum(y_true_f) + K.sum(y_pred_f) + smooth)
    )


def dice_coef_loss(y_true, y_pred):
    return 1 - dice_coef(y_true, y_pred)


# To Call the training in the terminal


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--path_training", required=True, help="")
    ap.add_argument("-m", "--path_model", required=True, help="")
    ap.add_argument(
        "-co",
        "--config_file",
        required=False,
        help="",
        default="~/.axondeepseg.json",
    )
    ap.add_argument("-m_init", "--path_model_init", required=False, help="")
    ap.add_argument("-gpu", "--GPU", required=False, help="")

    args = vars(ap.parse_args())
    path_training = Path(args["path_training"])
    path_model = Path(args["path_model"])
    path_model_init = Path(args["path_model_init"])
    config_file = args["config_file"]
    gpu = args["GPU"]

    config = generate_config(config_file)

    train_model(path_training, path_model, config, path_model_init, gpu=gpu)


if __name__ == "__main__":
    main()

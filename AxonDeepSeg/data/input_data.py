from skimage import exposure
from scipy.misc import imread
from scipy import ndimage
import numpy as np
import random
import os
from data_augmentation import shifting, rescaling, flipping, random_rotation, elastic
import functools
#import matplotlib.pyplot as plt

def generate_list_transformations(transformations = {}, thresh_indices = [0,0.5]):
    
    L_transformations = []
    if transformations == {}:
        L_transformations = [shifting, functools.partial(rescaling,thresh_indices=[0,0.5]),
                       functools.partial(random_rotation, thresh_indices=[0,0.5]), 
                       functools.partial(elastic,thresh_indices=[0,0.5]), flipping]    
    else:
        for k,v in transformations.iteritems():
            k = k.split('_')[-1]
            if v == True:
                if k.lower() == 'shifting':
                    L_transformations.append(shifting)
                elif k.lower() == 'rescaling':
                    L_transformations.append(functools.partial(rescaling,thresh_indices=[0,0.5]))
                elif k.lower() == 'random_rotation':
                    L_transformations.append(functools.partial(random_rotation,thresh_indices=[0,0.5]))
                elif k.lower() == 'elastic':
                    L_transformations.append(functools.partial(elastic,thresh_indices=[0,0.5]))
                elif k.lower() == 'flipping':
                    L_transformations.append(flipping)
                    
    return L_transformations


def all_transformations(patch, thresh_indices = [0,0.5], transformations = {}):
    """
    :param patch: [image,mask].
    :param thresh_indices : list of float in [0,1] : the thresholds for the ground truthes labels.
    :return: application of the random transformations to the pair [image,mask].
    """
    
    L_transformations = generate_list_transformations(transformations, thresh_indices)
                    
    for transfo in L_transformations:
        patch = transfo(patch)
       
    return patch

def random_transformation(patch, thresh_indices = [0,0.5], transformations = {}):
    """
    :param patch: [image,mask].
    :param thresh_indices : list of float in [0,1] : the thresholds for the ground truthes labels.
    :return: application of a random transformation to the pair [image,mask].
    """
    
    L_transformations = generate_list_transformations(transformations, thresh_indices)
                    
    patch = random.choice(L_transformations)(patch)
       
    return patch

def patch_to_mask(patch, thresh_indices=[0, 0.5]):
    '''
    Process a patch so that the pixels between two threshold values are set to the closest threshold, effectively
    enabling the creation of a mask with as many different values as there are thresholds.
    '''

    for indice,value in enumerate(thresh_indices[:-1]):
        if np.max(patch[1]) > 1.001:
            thresh_inf = np.int(255*value)
            thresh_sup = np.int(255*thresh_indices[indice+1])
        else:
            thresh_inf = value
            thresh_sup = thresh_indices[indice+1]   

            patch[1][(patch[1] >= thresh_inf) & (patch[1] < thresh_sup)] = np.mean([value,thresh_indices[indice+1]])

            patch[1][(patch[1] >= thresh_indices[-1])] = 1

    return patch


#######################################################################################################################
#                                             Input data for the U-Net                                                #
#######################################################################################################################
class input_data:
    """
    Data to feed the learning/validating of the CNN
    """

    def __init__(self, trainingset_path, type_ = 'train', batch_size = 8, thresh_indices = [0,0.5], image_size = 256):
        """
        Input: 
            trainingset_path : string : path to the trainingset folder containing 2 folders Validation and Train
                                    with images and ground truthes.
            type_ : string 'train' or 'validation' : for the network's training.
            thresh_indices : list of float in [0,1] : the thresholds for the ground truthes labels.
        Output:
            None.
        """
        if type_ == 'train' : # Data for train
            self.path = trainingset_path+'/Train/'
            self.set_size = len([f for f in os.listdir(self.path) if ('image' in f)])
            self.each_sample_once = False

        if type_ == 'validation': # Data for validation
            self.path = trainingset_path+'/Validation/'
            self.set_size = len([f for f in os.listdir(self.path) if ('image' in f)])
            self.each_sample_once = True

        self.size_image = image_size
        self.n_labels = 2
        self.samples_seen = 0
        self.thresh_indices = thresh_indices        
        self.batch_size = batch_size
        self.samples_list = self.reset_set(type_=type_)
        self.epoch_size = len(self.samples_list)


    def get_size(self):
        return self.set_size
    
    def reset_set(self, type_= 'train', shuffle=True):
        '''
        Reset the set.
        :param shuffle: If True, the set is shuffled, so that each batch won't systematically contain the same images.
        :return list: List of ids of training samples
        '''
        
        self.sample_seen = 0
        
        if type_ == 'train':
            # Generation of a shuffled list of images      
            samples_list = range(self.set_size)
            if shuffle:
                np.random.shuffle(samples_list)

            # Adding X images so that all batches have the same size.
            rem = self.set_size % self.batch_size
            if rem != 0:
                samples_list += np.random.choice(samples_list, rem, replace=False).tolist()
        else:
            samples_list = range(self.set_size)
            
        return samples_list


    def next_batch(self, augmented_data = {'type':'None', 'transformations':{}}, each_sample_once=False):
        """
        :param augmented_data: if True, each patch of the batch is randomly transformed with the data augmentation process.
        :return: The pair [batch_x (data), batch_y (prediction)] to feed the network.
        """
                
        batch_x = []
        batch_y = []

        # Set the range of indices
        # Read the image and mask files.
        for i in range(self.batch_size) :
            # We take the next sample to see
            indice = self.samples_list.pop(0)
            self.sample_seen += 1

            # We are reading directly the images. Range of values : 0-255
            image = imread(self.path + 'image_%s.png' % indice, flatten=False, mode='L')
            mask = imread(self.path + 'mask_%s.png' % indice, flatten=False, mode='L')            
            
            # Online data augmentation
            if augmented_data['type'].lower() == 'all':
                [image, mask] = all_transformations([image, mask], 
                                                    transformations = augmented_data['transformations'], 
                                                    thresh_indices = self.thresh_indices) 
            elif augmented_data['type'].lower() == 'random':
                [image, mask] = random_transformation([image, mask], 
                                                      transformations = augmented_data['transformations'], 
                                                      thresh_indices = self.thresh_indices)
            else:
                pass
            
            mask = patch_to_mask(mask, self.thresh_indices)
            
                
            #-----PreProcessing --------
            image = exposure.equalize_hist(image) #histogram equalization
            image = (image - np.mean(image))/np.std(image) #data whitening
            #---------------------------
            
            n = len(self.thresh_indices)

            # Working out the real mask (sparse cube with n depth layer for each class)
            real_mask = np.zeros([mask.shape[0], mask.shape[1], n])
            for class_ in range(n-1):
                real_mask[:,:,class_] = (mask[:,:] >= self.thresh_indices[class_]) * (mask[:,:] <                                    self.thresh_indices[class_+1])
            real_mask[:,:,n-1] = (mask > self.thresh_indices[n-1])
            real_mask = real_mask.astype(np.uint8)

            batch_x.append(image)
            batch_y.append(real_mask)
            
            # If we are at the end of an epoch, we reset the list of samples, so that during next epoch all sets will be different.
            if self.sample_seen == self.epoch_size:
                if each_sample_once:
                    self.samples_list = self.reset_set(type_ = 'validation')
                    break
                else:
                    self.samples_list = self.reset_set(type_ = 'train')

        
        # Ensuring that we do have np.arrays of the good size for batch_x and batch_y before returning them 
        return transform_batches([batch_x, batch_y])


    def next_batch_WithWeights(self, augmented_data = {'type':'None', 'transformations':{}}, each_sample_once=False):        
        """
        :param augmented_data: if True, each patch of the batch is randomly transformed with the data augmentation process.
        :return: The triplet [batch_x (data), batch_y (prediction), weights (based on distance to edges)] to feed the network.
        """
        batch_x = []
        batch_y = []
        batch_w = []
        
        for i in range(self.batch_size) :
            # We take the next sample to see
            indice = self.samples_list.pop(0)
            self.sample_seen += 1

            image = imread(self.path + 'image_%s.png' % indice, flatten=False, mode='L')
            mask = imread(self.path + 'mask_%s.png' % indice, flatten=False, mode='L')

            # Online data augmentation
            if augmented_data['type'].lower() == 'all':
                [image, mask] = all_transformations([image, mask], 
                                                    transformations = augmented_data['transformations'], 
                                                    thresh_indices = self.thresh_indices) 
            elif augmented_data['type'].lower() == 'random':
                [image, mask] = random_transformation([image, mask], 
                                                      transformations = augmented_data['transformations'], 
                                                      thresh_indices = self.thresh_indices)
            else:
                pass
            mask = patch_to_mask(mask, self.thresh_indices)

            #-----PreProcessing --------
            image = exposure.equalize_hist(image) #histogram equalization
            image = (image - np.mean(image))/np.std(image) #data whitening
            #---------------------------

            # Create a weight map for each class (background is the first class, equal to 1
            
            
            weights_intermediate = np.ones((self.size_image * self.size_image,len(self.thresh_indices)))
            #weights_intermediate = np.zeros((self.size_image, self.size_image, len(self.thresh_indices[1:])))

            for indice,classe in enumerate(self.thresh_indices[1:]):

                mask_classe = np.asarray(list(mask))
                if classe!=self.thresh_indices[-1]:
                    mask_classe[mask_classe != np.mean([self.thresh_indices[indice - 1], classe])] = 0
                    mask_classe[mask_classe==np.mean([self.thresh_indices[indice-1],classe])]=1
                else:
                    mask_classe[mask_classe!=1]=0

                to_use = np.asarray(255*mask_classe,dtype='uint8')
                to_use[to_use <= np.min(to_use)] = 0
                weight = ndimage.distance_transform_edt(to_use)
                weight[weight==0]=np.max(weight)

                if classe == self.thresh_indices[1]:
                    w0 = 0.5
                else :
                    w0 = 1

                sigma = 2
                weight = 1 + w0*np.exp(-(weight/sigma)**2/2)
                #weight = weight/np.max(weight)
                weights_intermediate[:,indice] = weight.reshape(-1, 1)[:,0]
                #weights_intermediate[:, :, indice] = weight

                """plt.figure()
                plt.subplot(2,2,1)
                plt.imshow(mask,cmap='gray')
                plt.title('Ground truth')
                plt.subplot(2,2,2)
                plt.imshow(weight, interpolation='nearest', cmap='gray',vmin=1)
                plt.title('Weight map')
                plt.colorbar(ticks=[1, 10])
                plt.show()"""
            
            # Generating the mask with the real labels as well as the matrix of the weights
            
            n = len(self.thresh_indices) #number of classes

            weights_intermediate = np.reshape(weights_intermediate,[mask.shape[0], mask.shape[1], n])
            
            # Working out the real mask (sparse cube with n depth layer for each class)
            real_mask = np.zeros([mask.shape[0], mask.shape[1], n])
            for class_ in range(n-1):
                real_mask[:,:,class_] = (mask[:,:] >= self.thresh_indices[class_]) * (mask[:,:] <                                    self.thresh_indices[class_+1])
            real_mask[:,:,n-1] = (mask > self.thresh_indices[n-1])
            real_mask = real_mask.astype(np.uint8)
            
            # Working out the real weights (sparse matrix with the weights associated with each pixel)
            
            real_weights = np.zeros([mask.shape[0], mask.shape[1]])            
            for class_ in range(n):
                real_weights += np.multiply(real_mask[:,:,class_],weights_intermediate[:,:,class_])
                
            
            # We have now loaded the good image, a mask (under the shape of a matrix, with different labels) that still needs to be converted to a volume (meaning, a sparse cube where each layer of depth relates to a class)
            
            batch_x.append(image)
            batch_y.append(real_mask)
            batch_w.append(real_weights)
            
            # If we are at the end of an epoch, we reset the list of samples, so that during next epoch all sets will be different.
            if self.sample_seen == self.epoch_size:
                if each_sample_once:
                    self.samples_list = self.reset_set(type_ = 'validation')
                    break
                else:
                    self.samples_list = self.reset_set(type_ = 'train')


        # Ensuring that we do have np.arrays of the good size for batch_x and batch_y before returning them        
        return transform_batches([batch_x, batch_y, batch_w])

    def read_batch(self, batch_y, size_batch):
        images = batch_y.reshape(size_batch, self.size_image, self.size_image, self.n_labels)
        return images
    
    
def transform_batches(list_batches):
    '''
    Transform batches so that they are readable by Tensorflow (good shapes)
    :param list_batches: [batch_x, batch_y, (batch_w)]
    :return transformed_batches: Returns the batches with good shapes for tensorflow
    '''
    batch_x = list_batches[0]
    batch_y = list_batches[1]
    if len(list_batches) == 3:
        batch_w = list_batches[2]
        
    if len(batch_y) == 1: # If we have only one image in the list np.stack won't work
        transformed_batches = []
        transformed_batches.append(np.reshape(batch_x[0], (1, batch_x[0].shape[0], batch_x[0].shape[1])))
        transformed_batches.append(np.reshape(batch_y[0], (1, batch_y[0].shape[0], batch_y[0].shape[1], -1)))
        
        if len(list_batches) == 3:
            transformed_batches.append(np.reshape(batch_w[0], (1, batch_w[0].shape[0], batch_w[0].shape[1])))
            
    else:
        transformed_batches = [np.stack(batch_x), np.stack(batch_y)]
         
        if len(list_batches) == 3:
            transformed_batches.append(np.stack(batch_w))
        
    return transformed_batches
    
    
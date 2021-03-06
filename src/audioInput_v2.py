#!apt-get install ffmpeg -y
#from audioUtils import readFolderRecursive
import random
import numpy as np
from audioUtils import readFolder, readFolderRecursive, load
from audioInput import readFolderRecursive, calculateSamplesForChunks, calculateChunksForSamples, calculateChunksForMs, calculateMsForChunks
from audio_transforms import mixWithFolder
from audio_transforms import changeGain, addCompression, changePitch
from tqdm import tqdm
import math
from src.AudioData import AudioData
from vggish_input import waveform_to_examples
audioData = AudioData()

SAMPLE_RATE = 44100
def getOneHot(class_num, idx):
    arr = np.zeros(class_num)
    arr[idx] = 1
    return arr

def getPosition(i, channels = 1):
    #mult = 16
    mult = 8 * channels
    # return (calculateSamplesForChunks(i) + (i * mult))
    return (calculateMsForChunks(i) + (i * mult))

cache = {}
def gatherData(files, transforms = [], start_at_zero = False):
    chunks_of_audio = []
    # print('gathering data for %i files' % (len(files)))

    for i in tqdm(range(0, len(files))):
        file = files[i]
        if file in cache:
            audio_segment = cache[file]
        else:
            audio_segment = load(file)
            cache[file] = audio_segment
        starting_index = 0
        if start_at_zero:
            starting_index = random.randint(0, calculateMsForChunks(1))

        sliced_audio = audio_segment[starting_index:]

        audio = None
        if len(transforms) == 0:
            audio = sliced_audio
        else:
            for transform in transforms:
                transformed_audio = transform(sliced_audio)
                assert len(sliced_audio) == len(transformed_audio), "Length of transformed audio doesn't match, orig: %i, transformed: %i" % (len(sliced_audio), len(transformed_audio))
                if audio is None:
                    audio = transformed_audio
                else:
                    audio += transformed_audio

        samples = audio.get_array_of_samples()
        # print('samples', len(samples))
        expected_chunks = calculateChunksForSamples(len(samples))
        # print('expected_chunks', expected_chunks)
        assert expected_chunks == len(waveform_to_examples(np.array(samples), SAMPLE_RATE)), "vggish does not match expected samples"
        for i in range(0, expected_chunks):
            start = getPosition(i)
            end = getPosition(i + 1)
            if start < len(audio):
                # chunk_of_samples = samples[start:end]
                # chunk_of_audio = audio._spawn(chunk_of_samples)
                chunk_of_audio = audio[start:end]
                chunks_of_audio.append({
                    'audio': chunk_of_audio,
                    'file': file,
                    'starting_index': starting_index + start,
                })
    return chunks_of_audio

def splitData(data, split):
    size = len(data)
    big = data[:round(size * (1 - split))]
    small = data[round(size * (1 - split)):]
    return big, small

"""Takes a number of dirs, gathers chunks for each file in that dir,
and then processes those chunks to return x and y
"""
def gatherTrainingDataWithCaching(dirs, augment_folders, should_balance = True, number_of_augmentations = 1):
    fileDirs = []
    augmentations = {}
    for i, d in enumerate(dirs):
        files = readFolderRecursive(d)
        fileDirs.append(files)

        augment_folder = augment_folders[i]
        if augment_folder:
            aug = mixWithFolder(augment_folder, [
                    {'name': 'gain', 'fn': lambda audio: changeGain(audio, 20, 10) },
                    {'name': 'compression', 'fn': lambda audio: addCompression(audio) },
                    # this messes the timing of the sample when running through vggish.
                    # need to find a method that doesn't change the audio length
                    #{'name': 'pitch', 'fn': lambda audio: changePitch(audio, -0.3, max=0.3) },
                ])
            augs = []
            for _ in range(number_of_augmentations):
                augs.append(aug)
            augmentations[i] = augs
        else:
            augmentations[i] = []

    def curriedFn(split = 0.2, shuf = True):
        chunks_of_audio = []
        for i, files in enumerate(fileDirs):
            transforms = augmentations[i]
            if len(transforms) == 0:
                print('training data, no transforms, %i files' % (len(files)))
            else:
                print('training data, %i transforms, %i files' % (len(transforms), len(files)))
            chunks = gatherData(files, transforms = transforms)
            label = getOneHot(len(dirs), i)
            for chunk in chunks:
                chunk['label'] = label

            chunks_of_audio += chunks

        if should_balance:
            chunks_of_audio = balanceData(chunks_of_audio)

        if shuf:
            random.shuffle(chunks_of_audio)
        train, test = splitData(chunks_of_audio, split)
        #return train
        return preprocessForTraining(train), preprocessForTraining(test)
    return curriedFn

def fillUp(arr, m):
    times = math.floor(m/len(arr))
    remainder = m - (times * len(arr))
    return arr * times + arr[0:remainder]

def balanceData(chunks):
    chunks_by_label = {}
    for chunk in chunks:
        label = chunk['label'].tostring()
        if label not in chunks_by_label:
            chunks_by_label[label] = []
        chunks_by_label[label].append(chunk)
    amount = 0
    for key in chunks_by_label.keys():
        if len(chunks_by_label[key]) > amount:
            amount = len(chunks_by_label[key])
    chunks = []
    for key in chunks_by_label.keys():
        filled_up_chunks = fillUp(chunks_by_label[key], amount)
        chunks += filled_up_chunks
    return chunks

def gatherTrainingData(dirs, split = .2, shuf = True, augment_folders = None):
    print('gathering training data')
    chunks_of_audio = []
    for i, d in enumerate(dirs):
        files = readFolderRecursive(d)
        print('gathering training data for', files)
        transforms = []
        augment_folder = augment_folders[i]

        if augment_folder is not '' and augment_folder is not None:
            transforms = [
                #lambda audio: audio,
                #lambda audio: changePitch(audio, min = -0.5, max = 0.5),
                #lambda audio: changeGain(audio),
                #lambda audio: addCompression(audio),
                mixWithFolder(augment_folder, [
                    lambda audio: changeGain(audio, 20, 10),
                    lambda audio: changePitch(audio, -0.3, max=0.3),
                    lambda audio: addCompression(audio),
                ]),
            ]
        chunks = gatherData(files, transforms = transforms)

        label = getOneHot(len(dirs), i)
        for chunk in chunks:
            chunk['label'] = label

        chunks_of_audio += chunks
    if shuf:
        random.shuffle(chunks_of_audio)
    train, test = splitData(chunks_of_audio, split)
    #return train
    return preprocessForTraining(train), preprocessForTraining(test)

def gatherTestingData(files):
    chunks = gatherData(files, transforms = [], start_at_zero = True)
    samples, labels = preprocessForTraining(chunks, False)
    return samples, chunks

def concatSamples(chunks):
    all_samples = None
    for chunk in chunks:
        if 'samples' in chunk:
            samples = chunk['samples']
            if all_samples is None:
                all_samples = samples
            else:
                all_samples = np.concatenate((all_samples,samples), axis=0)
    return all_samples

# def preprocessForTesting(chunks):
#     for i, chunk in enumerate(chunks):
#         audio = chunk['audio']
#         samples = audio.get_array_of_samples()
#         expected_chunks = calculateChunksForSamples(len(samples))
#         expected_chunks_for_ms = calculateChunksForMs(len(audio))
#         # print('chunks', expected_chunks, expected_chunks_for_ms, len(audio))
#         assert expected_chunks <= 1, "Expected chunks is greater than 1, something is dearly wrong, %i, %s " % (expected_chunks, chunk['file'])
#         if expected_chunks > 0:
#             vggish_samples = audioData.getSamplesAsVggishInput(samples)
#             chunk['samples'] = vggish_samples

#     return concatSamples(chunks), chunks


def preprocessForTraining(chunks, check_labels = True):
    all_samples = None
    labels = []
    print('preprocess for training', len(chunks))

    for i in tqdm(range(0, len(chunks))):
        chunk = chunks[i]
        audio = chunk['audio']
        samples = audio.get_array_of_samples()
        expected_chunks = calculateChunksForSamples(len(samples))
        expected_chunks_for_ms = calculateChunksForMs(len(audio))

        assert expected_chunks <= 1, "Expected chunks is %i and should be 1 or less, something is dearly wrong, %s " % (expected_chunks, chunk['file'])

        if expected_chunks > 0:
            vggish_samples = audioData.getSamplesAsVggishInput(samples)
            assert len(vggish_samples) == 1, "VGGish returned not 1, but %i: %s, starting index: %s, enumerated index: %i " % (len(vggish_samples), chunk['file'], chunk['starting_index'], i)
            chunk['samples'] = vggish_samples
    for chunk in chunks:
        if 'samples' in chunk and 'label' in chunk:
            labels.append(chunk['label'])
    all_samples = concatSamples(chunks)
    assert np.array(all_samples).shape[1] == 96, "Check shape of final samples, %s" % (np.array(all_samples).shape)
    if check_labels:
        assert len(labels) == len(all_samples), "Sizes don't match post vggish calc, labels: %i, samples: %i" % (len(labels), len(all_samples))

    return all_samples, labels

from collections import OrderedDict
import h5py
import mne
import numpy as np
from mne import create_info
from mne.io import RawArray
from scipy.io import loadmat
import os.path as osp
import zipfile as z

from moabb.datasets import download as dl
from moabb.datasets.base import BaseDataset


Castillos2023_URL = "https://zenodo.org/records/8255618"


# Each trial contained 12 cycles of a 2.2 second code
NR_CYCLES_PER_TRIAL = 15



def code2array(event_id):
    codes = OrderedDict()
    for k, v in event_id.items():
        code = k.split('_')[0]
        code = code.replace('.','').replace('2','')
        codes[v-1] = np.array(list(map(int, code)))
    
    return codes

class BaseCastillos2023(BaseDataset):
    """c-VEP and Burst-VEP dataset from Castillos et al. (2023)

    Dataset [1]_ from the study on burst-VEP [2]_.

    .. admonition:: Dataset summary

        =============  =======  =======  ==============================  ===============  ===============  ===========
        Name             #Subj    #Chan     #Trials / class              Trials length    Sampling rate      #Sessions
        =============  =======  =======  ==============================  ===============  ===============  ===========
        Castillos2023       12       32   15 "1"/15 "2"/ 15 "3"/ 15 "4"  0.25s             500Hz                     1
        =============  =======  =======  ==============================  ===============  ===============  ===========

    **Dataset description**

    Participants were comfortably seated and instructed to read and sign the informed consent. EEG data were recorded 
    using a BrainProduct LiveAmp 32 active electrodes wet-EEG setup with a sample rate of 500 Hz to record the surface 
    brain activity. The 32 electrodes were placed following the 10–20 international system on a BrainProduct Acticap. The 
    ground electrode was placed at the FPz electrode location and all electrodes were referenced to the FCz electrode. The 
    impedance of all electrodes was brought below 25kΩ prior to recording onset. Once equipped with the EEG system, 
    volunteers were asked to focus on four targets that were cued sequentially in a random order for 0.5 s, followed by a 
    2.2 s stimulation phase, before a 0.7 s inter-trial period. The cue sequence for each trial was pseudo-random and 
    different for each block. After each block, a pause was observed and subjects had to press the space bar to continue. 
    The participants were presented with fifteen blocks of four trials for each of the four conditions (burst or msequence × 
    40% or 100%), see Fig. 2 - left. The task was implemented in Python using the Psychopy toolbox.1 The four discs were all 
    150 pixels, without borders, and were presented on the following LCD monitor: Dell P2419HC, 1920 × 1080 pixels, 265 
    cd/m2, and 60 Hz refresh rate. After completing the experiment and removing the EEG equipment, the participants were 
    asked to provide subjective ratings for the different stimuli conditions. These stimuli included burst c-VEP with 100% 
    amplitude, burst c-VEP with 40% amplitude, m-sequences with 100% amplitude, and m-sequences with 40% amplitude. Each 
    stimulus was presented three times in a pseudo-random order. Following the presentation of each stimulus, participants 
    were presented with three 11-points scales and were asked to rate the visual comfort, visual tiredness, and 
    intrusiveness using a mouse. In total, participants completed 12 ratings (3 repetitions 𝑥 4 types of stimuli) for 
    each of the three scales.

    References
    ----------

    .. [1] Kalou Cabrera Castillos. (2023). 4-class code-VEP EEG data [Data set]. Zenodo.(dataset).
           DOI: https://doi.org/10.5281/zenodo.8255618

    .. [2] Kalou Cabrera Castillos, Simon Ladouce, Ludovic Darmet, Frédéric Dehais. Burst c-VEP Based BCI: Optimizing stimulus 
           design for enhanced classification with minimal calibration data and improved user experience,NeuroImage,Volume 284,
           2023,120446,ISSN 1053-8119
           DOI: https://doi.org/10.1016/j.neuroimage.2023.120446

    Notes
    -----

    .. versionadded:: 0.6.0

    """

    def __init__(self, events, sessions_per_subject, code, paradigm,paradigm_type,window_size=0.25):
        super().__init__(
            subjects=list(range(1, 12 + 1)),
            sessions_per_subject=sessions_per_subject,
            events=events,
            code=code,
            interval=(0, 0.25),
            paradigm=paradigm,
            doi="https://doi.org/10.1016/j.neuroimage.2023.120446",
        )
        self.paradigm_type = paradigm_type
        self.sfreq = 500
        self.fps = 60
        self.n_channels = 32
        self.window_size = window_size
    
    def _add_stim_channel_trial(
        self, raw, onsets, labels, offset=200, ch_name="stim_trial"
    ):
        """
        Add a stimulus channel with trial onsets and their labels.

        Parameters
        ----------
        raw: mne.Raw
            The raw object to add the stimulus channel to.
        onsets: List | np.ndarray
            The onsets of the trials in sample numbers.
        labels: List | np.ndarray
            The labels of the trials.
        offset: int (default: 200)
            The integer value to start markers with. For instance, if 200, then label 0 will be marker 200, label 1
            will be be marker 201, etc.
        ch_name: str (default: "stim_trial")
            The name of the added stimulus channel.
        Returns
        -------
        mne.Raw
            The raw object with the added stimulus channel.
        """
        stim_chan = np.zeros((1, len(raw)))
        for onset, label in zip(onsets, labels):
            stim_chan[0, onset] = offset + label
        info = create_info(
            ch_names=[ch_name],
            ch_types=["stim"],
            sfreq=raw.info["sfreq"],
            verbose=False,
        )
        raw = raw.add_channels([RawArray(data=stim_chan, info=info, verbose=False)])
        return raw

    def _add_stim_channel_epoch(
        self,
        raw,
        onsets,
        labels,
        offset=100,
        ch_name="stim_epoch",
    ):
        """
        Add a stimulus channel with epoch onsets and their labels, which are the values of the presented code for each
        of the trials.

        Parameters
        ----------
        raw: mne.Raw
            The raw object to add the stimulus channel to.
        onsets: List | np.ndarray
            The onsets of the trials in sample numbers.
        labels: List | np.ndarray
            The labels of the trials.
        codes: np.ndarray
            The codebook containing each presented code of shape (nr_bits, nr_codes), sampled at the presentation rate.
        offset: int (default: 100)
            The integer value to start markers with. For instance, if 100, then label 0 will be marker 100, label 1
            will be be marker 101, etc.
        ch_name: str (default: "stim_epoch")
            The name of the added stimulus channel.
        Returns
        -------
        mne.Raw
            The raw object with the added stimulus channel.
        """
        stim_chan = np.zeros((1, len(raw)))
        for onset, label in zip(onsets, labels):
            stim_chan[0, int(onset*self.sfreq)] = offset + label #codes[:, label]
        info = create_info(
            ch_names=[ch_name],
            ch_types=["stim"],
            sfreq=raw.info["sfreq"],
            verbose=False,
        )
        raw = raw.add_channels([RawArray(data=stim_chan, info=info, verbose=False)])
        return raw

    def _get_single_subject_data(self, subject):
        """Return the data of a single subject."""
        file_path_list = self.data_path(subject,self.paradigm_type)

        raw = mne.io.read_raw_eeglab(file_path_list[0],preload=True, verbose=False)


        # Strip the annotations that were script to make them easier to process
        events, event_id = mne.events_from_annotations(raw, event_id='auto', verbose=False)
        to_remove = []
        for idx in range(len(raw.annotations.description)):
            if (('collects' in raw.annotations.description[idx]) or
                ('iti' in raw.annotations.description[idx]) or
                (raw.annotations.description[idx] == '[]')):
                to_remove.append(idx)
            else:
                code = raw.annotations.description[idx].split('_')[0]
                lab = raw.annotations.description[idx].split('_')[1]
                code = code.replace('\n', '')
                code = code.replace('[', '')
                code = code.replace(']', '')
                code = code.replace(' ', '')
                raw.annotations.description[idx] = code + '_' + lab
        to_remove = np.array(to_remove)
        if len(to_remove) > 0:
            raw.annotations.delete(to_remove)

        # Get the labels and data 
        events, event_id = mne.events_from_annotations(raw, event_id='auto', verbose=False)
        shift = 0.0
        epochs = mne.Epochs(raw, events, event_id=event_id, tmin=shift, \
                    tmax=2.2+shift, baseline=(None, None), preload=False, verbose=False)
        labels = epochs.events[..., -1]
        onset_code = epochs.events[..., 0]
        labels -= np.min(labels)
        data = epochs.get_data()
        self.codes = self.__code2array(event_id)
        
        n_samples_windows = int(self.window_size*self.sfreq)

        # Get the windows epoch of each frame, the label of each frame and the onset for each frame in sample time
        raw_window, y_window, frame_taken = self.__to_window_by_frame(data,labels,n_samples_windows,self.codes)
        onset,onset_0 = self.__onset_anno(frame_taken,y_window,onset_code,1,60)

        # Create stim channel with trial information (i.e., symbols)
        # Specifically: 200 = symbol-0, 201 = symbol-1, 202 = symbol-2, etc.
        raw = self._add_stim_channel_trial(
            raw, onset_code, labels, offset=200
        )
        # Create stim channel with epoch information (i.e., 1 / 0, or on / off)
        # Specifically: 100 = "0", 101 = "1"
        raw = self._add_stim_channel_epoch(
            raw, np.concatenate([onset,onset_0]), np.concatenate([np.ones(onset.shape),np.zeros(onset_0.shape)]), offset=100
        )
        
        # Put the reference to the average
        mne.set_eeg_reference(raw, 'average', copy=False, verbose=False)

        
        # There is only one session, one trial of 60 subtrials
        sessions = {"0": {}}
        sessions["0"]["0"] = raw

        return sessions

    def __code2array(self,event_id):
        """ Return the code of the event ID in a good format """
        codes = OrderedDict()
        for k, v in event_id.items():
            code = k.split('_')[0]
            code = code.replace('.','').replace('2','')
            codes[v-1] = np.array(list(map(int, code)))
        return codes


    def data_path(
        self, subject, paradigm_type, path=None, force_update=False, update_path=None, verbose=None
    ):
        """Return the data paths of a single subject."""
        if subject not in self.subject_list:
            raise (ValueError("Invalid subject number"))
        
        subject_paths = []

        url = "https://zenodo.org/records/8255618/files/4Class-CVEP.zip"
        path_zip = dl.data_dl(url, "4Class-VEP",path="C:\\Users\\s.velut\\Documents\\These\\Protheus_PHD")
        path_folder = "C"+path_zip.strip("4Class-VEP.zip")

        # check if has to unzip
        if not (osp.isdir(path_folder + "4Class-VEP")):
            zip_ref = z.ZipFile(path_zip, "r")
            zip_ref.extractall(path_folder)

        subject_paths.append(path_folder+"4Class-CVEP/P{:d}/P{:d}_{:s}.set".format(subject, subject, paradigm_type))

        return subject_paths

    def __to_window_by_frame(self,data, labels,n_samples_windows,codes,offset=0,
                        focus_rising=None):
        """
        Return the window epochs, the labels and the taken index of each frame during the presentation of the
        different stimuli

        Parameters
        ----------
        data: List | np.ndarray
            The data array of the epochs of the trials of the experiment.
        labels: List | np.ndarray
            The labels of the epochs(ie. frame)
        n_samples_windows: List | np.ndarray
            The number of sample time in the window.
        codes: np.ndarray
            The codebook containing each presented code of shape (nr_bits, nr_codes), sampled at the presentation rate.
        offset: int (default: 100)
            The integer value to start the window after the onset of the corresponding frame
        focus_rising: bool (default: "stim_epoch")
            Boolean to focus on the rising or on the all the code.
        Returns
        -------
        X : np.array 
            The array of the epoch starting at each frame.
        Y : np.array
            The array of the label of each epochs
        idx_taken : np.array
            The array of the array taken 
        """
        length = int((2.2-self.window_size)*self.fps)
        X = np.empty(shape=((length)*data.shape[0], self.n_channels, n_samples_windows))
        Y = np.empty(shape=((length)*data.shape[0]), dtype=int)
        idx_taken = []
        for trial_nb, trial in enumerate(data):
            lab = labels[trial_nb]
            c = codes[lab]
            labels_upsampled = np.repeat(c, self.fps//self.fps)
            labels_upsampled = np.concatenate((np.zeros(int(offset*self.fps), dtype=int), np.array(labels_upsampled)))
            if (focus_rising is not None):
                hi_indices = []
                for idx in range(1, len(labels_upsampled)):
                    if (focus_rising is not None) and (labels_upsampled[idx-1] == 0) and (labels_upsampled[idx] == 1):
                        hi_indices.append(idx)
                focused_labels = np.zeros(length)
                for idx in hi_indices:
                    focused_labels[idx:idx+4] = 1
                    # focused_labels[idx+1:idx+4] = -1
            else:
                focused_labels = labels_upsampled.copy()

            for idx in range(length):
                # print('Xidx:', trial_nb*length+idx, "Tidxm:", idx, 'TidxM:', idx +
                #       n_samples_windows, 'Ltrial', trial[:, idx:idx+n_samples_windows].shape)
                X[trial_nb*length+idx] = trial[:, idx:idx+n_samples_windows]
                Y[trial_nb*length+idx] = focused_labels[idx]
                idx_taken.append(trial_nb*length+idx)
        X = X.astype(np.float32)
        # X = np.delete(X,np.where(Y==-1),0)
        # idx_taken = np.delete(idx_taken,np.where(Y==-1))
        # Y = np.delete(Y,np.where(Y==-1))
        return X, Y, idx_taken

    def __onset_anno(self,onset_window,label_window,onset_code,nb_seq_min,nb_seq_max):
        """
        Return the onset in second of the frame where the flash is on and the onset in second of the frame where the flash is off

        Parameters
        ----------
        onset_window: List | np.ndarray
            The list of the onset of all the frame taken that appear in the stimuli
        label_window: List | np.ndarray
            The labels of the epochs(ie. frame)
        onset_code: List | np.ndarray
            The list of the onset of the first frame of each code
        nb_seq_min: int
            The first sequence (ie code) to start from
        nb_seq_max: int 
            The last sequence (ie code) + 1 to finish calcul of the onset
        Returns
        -------
        onset_1 : np.array 
            the onset in second of the frame where the flash is on
        onset_0 : np.array
            the onset in second of the frame where the flash is off
        """
        assert(self.sfreq!=0)
        new_onset = []
        new_onset_0 = []
        current_code = 0
        onset_code = np.ceil(onset_code*self.fps/self.sfreq)
        nb_seq_min-=1
        onset_shift = onset_code[current_code+nb_seq_min]
        time_trial = (2.2-self.window_size)
        # onset_window = np.arange(0,time_trial*fps*(nb_seq_max-nb_seq_min)-1,1,dtype=int)
        for i,o in enumerate(onset_window):
            if label_window[i]==1:
                # print(i)
                if current_code==nb_seq_max-1-nb_seq_min:
                    new_onset.append(o+onset_shift)
                else:
                    if o+onset_shift >= onset_code[current_code+nb_seq_min]+time_trial*self.fps:
                        current_code+=1
                        onset_shift = onset_code[current_code+nb_seq_min]-time_trial*self.fps*current_code
                    new_onset.append(o+onset_shift)
            else:
                if current_code==nb_seq_max-1-nb_seq_min:
                    new_onset_0.append(o+onset_shift)
                else:
                    if o+onset_shift >= onset_code[current_code+nb_seq_min]+time_trial*self.fps:
                        current_code+=1
                        onset_shift = onset_code[current_code+nb_seq_min]-time_trial*self.fps*current_code
                    new_onset_0.append(o+onset_shift)
        
        # modified_onset_code = [onset_code[i]-time_trial*sfreq*i for i in range(nb_seq_min,nb_seq_max)]
        # new_onset_0 = np.concatenate([np.arange(onset_code[i],onset_code[i]+time_trial*sfreq,sfreq//60) for i in range(nb_seq_min,nb_seq_max)])
        new_onset_0 = np.array(list(filter(lambda i: i not in new_onset, new_onset_0)))
        # print(new_onset_0.shape)
        return np.array(new_onset)/self.fps, np.array(new_onset_0)/self.fps
            


class CasitllosBurstVEP100(BaseCastillos2023):
    """BurstVEP CasitllosBurstVEP100 dataset.

    .. admonition:: Dataset summary


        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        Name                      #Subj    #Chan    #Classes    #Trials / class    Trials length    Sampling rate      #Sessions
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        CasitllosBurstVEP100       12      32            4      15                 2.2s               500Hz                    1
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========

    """

    def __init__(self):
        super().__init__(
            events={'0': 100,'1':101},
            sessions_per_subject=1,
            code="CasitllosBurstVEP100",
            paradigm="cvep",
            paradigm_type="burst100",
        )

class CasitllosBurstVEP40(BaseCastillos2023):
    """BurstVEP CasitllosBurstVEP40 dataset.

    .. admonition:: Dataset summary


        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        Name                      #Subj    #Chan    #Classes    #Trials / class    Trials length    Sampling rate      #Sessions
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        CasitllosBurstVEP40        12      32            4      15                 2.2s               500Hz                    1
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========

    """

    def __init__(self):
        super().__init__(
            events= {'0': 1,'1':2},
            sessions_per_subject=1,
            code="CasitllosBurstVEP40",
            paradigm="cvep",
            paradigm_type="burst40",
        )

class CasitllosCVEP100(BaseCastillos2023):
    """CVEP CasitllosCVEP100 dataset.

    .. admonition:: Dataset summary


        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        Name                      #Subj    #Chan    #Classes    #Trials / class    Trials length    Sampling rate      #Sessions
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        CasitllosCVEP100          12       32            4      15                 2.2s               500Hz                    1
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========

    """

    def __init__(self):
        super().__init__(
            events={'0':0,
                    '1':1},
            sessions_per_subject=1,
            code="CasitllosBurstVEP100",
            paradigm="cvep",
            paradigm_type="mseq100",
        )

class CasitllosCVEP40(BaseCastillos2023):
    """CVEP CasitllosCVEP40 dataset.

    .. admonition:: Dataset summary


        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        Name                      #Subj    #Chan    #Classes    #Trials / class    Trials length    Sampling rate      #Sessions
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========
        CasitllosCVEP40           12       32            4      15                 2.2s             500Hz                    1
        ====================      =======  =======  ==========  =================  ===============  ===============  ===========

    """

    def __init__(self):
        super().__init__(
            events={'111111111111110000111100001111000011001111001100001100111111000000110011111100001100110000001111001100000011001100001100000000001100_1': 1,
                    '000011110000000011111111110000000000001111000011001100110011110011000000110000001111110011001111111111000011000000111100001100111111_2': 2,
                    '111100000000110000111100000000000011001111001100110011000000111111001111110011001111000000111100111111000000000011111100001100110011_3': 3,
                    '111100111100111100111100000011111100000011111111110000110011000011110000000011000000001111111111110011001100001111000011000000110011_4': 4},
            sessions_per_subject=1,
            code="CasitllosBurstVEP40",
            paradigm="cvep",
            paradigm_type="mseq40",
        )
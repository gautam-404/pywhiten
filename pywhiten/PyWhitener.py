import tomli
from pywhiten.data import *
from pywhiten.pwio import OutputManager
from pywhiten.optimization.Optimizer import Optimizer
import os
import numpy as np


class PyWhitener:
    """
    The main class for conduction pre-whitening analyses using pywhiten.
    Attributes:
        lcs (list): A list of Lightcurve objects. The first entry is populated with the constructor, and subsequent
            entries are added when pre-whitening
        freqs (FrequencyContainer): A container of Frequency objects identified while pre-whitening
        cfg (dict): A nested dictionary representing the configuration supplied in [package path]/cfg/default.toml,
            or however manually specified
        optimizer (Optimizer): A class for handling the optimization steps of the pre-whitening process
    """
    lcs: list
    freqs: FrequencyContainer
    cfg: dict
    output_manager: OutputManager
    optimizer: Optimizer

    def __init__(self, time, data, err=None, cfg_file="default", cfg=None):
        """

        Args:
            time (np.ndarray): Time series time axis
            data (np.ndarray): Time series data axis
            err (np.ndarray): Time series data point weights, in the form of uncertainties
            cfg_file (string): Path to (or filename, if file is in current working directory or cfg directory) a config
                file, which will be used to overwrite the default configuration. Does not need to be fully populated,
                only the populated fields will overwrite.
            cfg (dict): A nested dict which mimics the structure of the configuration file. This can also be used to
                manually override the configuration entries. For example, to set the periodogram x labels the following
                should return the desired value: example_dict['output']['paths']['pg_x_label']
        """
        # using this method to load the cfg maintains backwards compatibility with python 3.7 in the least painful form
        # load default cfg, then overwrite with config file specified by cfg
        pkg_path = os.path.abspath(__file__)[:-14]
        default_config = pkg_path + "/cfg/default.toml"
        with open(default_config, "rb") as f:
            self.cfg = tomli.load(f)

        if cfg_file != "default" and type(cfg_file) == str:
            # if specified cfg file is in current directory, use that
            if os.path.exists(f"{os.getcwd()}/+{cfg_file}"):
                with open(f"{os.getcwd()}/+{cfg_file}", "rb") as f:
                    loaded_cfg = tomli.load(f)
                    self.cfg = merge_dict(self.cfg, loaded_cfg)
                self.cfg["title"] = "Config loaded from file in working directory"
            # try to find it in the cfg directory instead
            elif os.path.exists(f"{pkg_path}/cfg/{cfg_file}"):
                with open(f"{pkg_path}/cfg/{cfg_file}", "rb") as f:
                    loaded_cfg = tomli.load(f)
                    self.cfg = merge_dict(self.cfg, loaded_cfg)
                self.cfg["title"] = "Config loaded from file in package cfg directory"
            # finally, check to see if the cfg file was specified as a full path
            elif os.path.exists(cfg_file):
                with open(cfg_file, "rb") as f:
                    loaded_cfg = tomli.load(f)
                    self.cfg = merge_dict(self.cfg, loaded_cfg)
                self.cfg["title"] = "Config loaded from file at specified path"
        # use the cfg argument of the initializer to overwrite any cfg entries
        if cfg is not None and type(cfg) == dict:
            self.cfg = self.cfg = merge_dict(self.cfg, cfg)
            self.cfg["title"] += " - Merged with runtime-specified arguments"
        # handle special logic cases
        pass
        # config setup done
        # now set up initial light curve, frequency container, output mgr
        self.lcs = [Lightcurve(time, data, err)]
        self.freqs = FrequencyContainer()
        self.output_manager = OutputManager(cfg=self.cfg)
        self.optimizer = Optimizer(cfg = self.cfg)

        # we're now ready to do some frequency analysis

    def id_peak(self, method, idx=-1):
        """
        Gets a candidate frequency/amplitude pair from a periodogram belonging to a light curve in lcs list
        Args:
            method (str): A method used to identify a peak. Allowed values: ['highest', 'slf', 'poly', 'avg']. Refer
                to data.Periodogram.select_peak() for more details
            idx (int): index in lcs list to identify a peak from

        Returns:
            All values will be None if entire periodogram is excluded from selection. This can occur if using the 'slf'
            'poly' or 'avg' methods and no points in the periodogram meet the required minimum significance. In this
            case, this is utilized as a signal to trigger a stop criterion when automatically pre-whitening.
            float: candidate frequency
            float: candidate amplitude.
        """
        return self.lcs[idx].periodogram.select_peak(method=method,
                                                     min_prov_sig=self.cfg["autopw"]["peak_selection_cutoff_sig"])

    def it_pw(self, peak_selection_method="highest"):
        """
        Conducts a single pre-whitening iteration. Identifies a candidate frequency/amplitude from the most recent
        light curve, fits a single-frequency sinusoid to the most recent light curve and includes it as a frequency,
        improves all parameters of all frequencies in multi-frequency fit against original light curve, and makes a new
        light curve ready for another iteration.
        Args:
            peak_selection_method (str):  the peak selection method used to get a candidate frequency/amplitude. can be
                one of ['highest', 'slf', 'poly', 'avg'] - see id_peak method of data.Periodogram class

        Returns:
            bool: indicates pre-whitening iteration success
        """
        if self.cfg["output"]["print_runtime_messages"]:
            print(f"[pywhiten] ITERATION {self.freqs.n + 1}")

        # First stage, identify a candidate frequency/amplitude from the most recent periodogram
        candidate_frequency, candidate_amplitude = self.id_peak(method=peak_selection_method)

        # Second stage, conduct a single-frequency fit
        sf_f, sf_a, sf_p, sf_model = self.optimizer.single_frequency_optimization(self.lcs[-1].time,
                                                                         self.lcs[-1].data,
                                                                         self.lcs[-1].err,
                                                                         candidate_frequency, candidate_amplitude, 0.5)
        self.freqs.add_frequency(Frequency(f=sf_f, a=sf_a, p=sf_p, model_function=self.optimizer.sf_func,
                                           t0=self.cfg["input"]["input_t0"], n=len(self.freqs.get_flist())))
        if self.cfg["output"]["print_runtime_messages"]:
            print(f"[pywhiten] Identified single frequency model:")
            self.freqs.get_flist()[-1].prettyprint()

        # Third stage, conduct the multi-frequency fit
        mf_mod = self.optimizer.multi_frequency_optimization(self.lcs[0].time,
                                                             self.lcs[0].data,
                                                             self.lcs[0].err,
                                                             self.freqs.get_flist())

        self.output_manager.save_it(self.lcs, self.freqs, self.optimizer.c_zp)
        if self.cfg["output"]["print_runtime_messages"]:
            print(f"[pywhiten] Completed optimization of current complete variability model:")
            for f_to_print in self.freqs.get_flist():
                f_to_print.prettyprint()

        # Final Stage, make a new light curve and append it to the lightcurves list
        if self.cfg["autopw"]["new_lc_generation_method"] == "mf":
            self.lcs.append(Lightcurve(self.lcs[0].time, self.lcs[0].data - mf_mod, err = self.lcs[0].err))
            return True
        elif self.cfg["autopw"]["new_lc_generation_method"] == "sf":
            self.lcs.append(Lightcurve(self.lcs[-1].time, self.lcs[-1].data - sf_model, err=self.lcs[0].err))
            return True
        return False





def merge_dict(old_dict, new_dict):
    out_dict = {}
    for key in new_dict.keys():
        if key in old_dict.keys() and type(old_dict[key]) == dict:
            out_dict[key] = merge_dict(old_dict[key], new_dict[key])
        else:
            out_dict[key] = new_dict[key]
    for key in old_dict.keys():
        if key not in out_dict.keys():
            out_dict[key] = old_dict[key]
    return out_dict


if __name__ == "__main__":
    test_pywhitener = PyWhitener(np.linspace(0, 10, 100), np.random.rand(100), np.ones(100))
    print(test_pywhitener.cfg)

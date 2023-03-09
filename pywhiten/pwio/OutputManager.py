import os
import shutil
import numpy as np

import matplotlib.pyplot as pl
from pywhiten.pwio.utilities import flux2mag, flux2mag_e, format_output
from pywhiten.data.FrequencyContainer import FrequencyContainer


class OutputManager:
    """
        Handles output data/plots and associated formatting for lightcurves, periodograms, and other data from the
        pre-whitening analysis.
        Attributes:
            np.array model_x: An x-array used to make models of variability models, such that they can be plotted over LCs
            
            dict output_dirs: A dictionary of output directories, containing the following keyed values:
                string main_dir: The absolute path to the main output directory
                string pgs_output: The absolute path to the subdirectory where all periododgram data/plots are saved
                string pgs_slf_output: The absolute path to the subdirectory where periodograms are saved with slf fits overlaid
                string pgs_box_avg_output: "" box average profiles overlaid - Currently nothing is saved here
                string pgs_lopoly_output: "" Low-order polynomial fits overlaid, only the final periodogram is currently saved
                string pgs_data_output: The absolute path to the subdirectory where the raw data of each periodogram is saved
                string lcs_output: The absolute path to the subdirectory where all light curve data/plots are saved
                string lcs_sf_output: The absolute path to the subdirectory where light curve plots are saved with single-freq
                    variability models overlaid
                string lcs_mf_output: The absolute path to the subdirectory where light curves are saved with complete
                    variability models overplotted
                string lcs_data_output: The absolute path to the subdirectory where the raw data of residual light curves are
                    saved
                string misc_output: The absolute path where misc data and plots are saved
        """
    model_x: np.ndarray
    cfg: dict

    output_dirs = {"base": None,
                   "pgs_base": None,
                   "pgs_raw": None,
                   "pgs_slf": None,
                   "pgs_box": None,
                   "pgs_lopoly": None,
                   "lcs_base": None,
                   "lcs_raw": None,
                   "lcs_sf": None,
                   "lcs_mf": None,
                   "lcs_data": None,
                   "auxiliary": None}

    def __init__(self, cfg):
        # Make directories
        try:
            # set up base directory
            if cfg["output"]["paths"]["base"] in [".", "cwd", "/."]:
                self.output_dirs["base"] = os.getcwd()
            else:
                self.output_dirs["base"] = os.getcwd() + cfg["output"]["paths"]["base"]
            # set up second level directories
            for key in ["pgs_base", "lcs_base", "auxiliary"]:
                self.output_dirs[key] = self.output_dirs["base"] + cfg["output"]["paths"][key]
            # set up pgs directories
            for key in ["pgs_raw", "pgs_slf", "pgs_box", "pgs_lopoly"]:
                self.output_dirs[key] = self.output_dirs["pgs_base"] + cfg["output"]["paths"][key]
            # set up lcs directories
            for key in ["lcs_raw", "lcs_sf", "lcs_mf", "lcs_data"]:
                self.output_dirs[key] = self.output_dirs["lcs_base"] + cfg["output"]["paths"][key]
        except KeyError:
            raise KeyError("Issue with specified output directories")

        if os.path.exists(self.output_dirs["base"]):
            shutil.rmtree(self.output_dirs["base"])

        # now actually make the directories
        for path_key in self.output_dirs:
            os.makedirs(self.output_dirs[path_key], exist_ok=True)

    def save_it(self, lcs, freqs, zp):
        """
        Save the results from a single iteration. This is called at the end of each iteration.
        :param lcs: Current list of light curves stored in the parent Dataset obj
        :param freqs: Current list of frequencies stored in the parent Dataset obj
        :param zp: Current floating mean adjustment stored in the parent Dataset obj
        :return: None
        """
        n = len(freqs) - 1
        c_lc = lcs[-1]
        c_pg = c_lc.periodogram
        c_freq = freqs.get_flist()[-1]

        # Save LC, PG data
        self.save_lc(c_lc, f"{self.output_dirs['lcs_data']}/lc{n}.txt")
        self.save_pg(c_pg, f"{self.output_dirs['pgs_data']}/pg{n}.txt")

        # ================= LC PLOTS ===================
        # regular ======================================
        self.add_lc_plot_to_curfig(x=c_lc.time, y=c_lc.data)
        self.add_lc_formatting_to_curfig()
        pl.savefig(f"{self.output_dirs['lcs_raw']}/lc{n}.png")
        pl.clf()
        # sf ===========================================
        self.add_lc_plot_to_curfig(x=c_lc.time, y=c_lc.data, label="Data")
        self.add_lc_plot_to_curfig(x=self.model_x, y=c_freq.genmodel_sf(self.model_x), color="red", label="SF Model")
        self.add_lc_formatting_to_curfig(legend=True)
        pl.savefig(f"{self.output_dirs['lcs_sf']}/lc_sf{n}.png")
        pl.clf()
        # mf ===========================================
        self.add_lc_plot_to_curfig(x=lcs[0].time, y=lcs[0].data, label="Data")
        mf_y = np.zeros(len(self.model_x)) + zp
        for freq in freqs:
            mf_y += freq.genmodel(self.model_x)
        self.add_lc_plot_to_curfig(x=self.model_x, y=mf_y, color="red", label="Complete Variability Model")
        self.add_lc_formatting_to_curfig(legend=True)
        pl.savefig(f"{self.output_dirs['lcs_mf']}/lc_mf{n}.png")
        pl.clf()

        # ================= PG PLOTS ===================
        # regular ======================================
        self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.lsamp, label="Data")
        self.add_pg_formatting_to_curfig()
        pl.savefig(f"{self.output_dirs['pgs_raw']}/pg{n}.png")
        pl.clf()
        # slf ==========================================
        if c_pg.slf_p is not None:
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.lsamp, label="Data")
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.get_slf_model(c_pg.lsfreq), color="red", label="SLF Fit")
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq,
                                       y=c_pg.get_slf_model(c_pg.lsfreq) * self.cfg["autopw"][
                                           "peak_selection_cutoff_sig"],
                                       color="blue", label="Minimum Selection Amplitude", linestyle="--")
            self.add_pg_formatting_to_curfig(legend=True)
            pl.savefig(f"{self.output_dirs['pgs_slf']}/pg{n}.png")
            pl.clf()
        # lopoly =======================================
        if c_pg.polyparams_log is not None:
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.lsamp, label="Data")
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.get_polyfit_model(c_pg.lsfreq), color="red",
                                       label="LOPoly Fit")
            self.add_pg_formatting_to_curfig(legend=True)
            pl.savefig(f"{self.output_dirs['pgs_lopoly']}/pg{n}.png")
            pl.clf()

    def post_pw(self, lcs, freqs, zp):
        """
        Saves plots and data after the pre-whitening is complete and the post-prewhitening adjustments are made.
        :param lcs: Final list of light curves stored in the parent Dataset obj.
        :param freqs: Final list of Freq object stored in the parent Dataset obj.
        :param zp: Final floating mean adjustment stored in the parent Dataset obj.
        :return: None
        """
        n = len(lcs)
        c_lc = lcs[-1]
        c_pg = c_lc.periodogram

        # ================= LC PLOTS ===================
        # regular ======================================
        self.add_lc_plot_to_curfig(x=c_lc.time, y=c_lc.data)
        self.add_lc_formatting_to_curfig()
        pl.savefig(f"{self.output_dirs['lcs_base']}/lc{n}_final_residual.png")
        pl.clf()
        # mf ===========================================
        self.add_lc_plot_to_curfig(x=lcs[0].time, y=lcs[0].data, label="Data")
        mf_y = np.zeros(len(self.model_x)) + zp
        for freq in freqs:
            mf_y += freq.genmodel(self.model_x)
        self.add_lc_plot_to_curfig(x=self.model_x, y=mf_y, color="red", label="Complete Variability Model", linestyle="-", marker="")
        self.add_lc_formatting_to_curfig(legend=True)
        pl.savefig(f"{self.output_dirs['lcs_base']}/lc_mf{n}_final.png")
        pl.clf()

        # stdevs =======================================
        stdevs_x = np.array([x for x in range(len(lcs))])
        stdevs_y = np.array([np.std(flux2mag(lc.data, self.rflux) * 1000) for lc in lcs])
        pl.plot(stdevs_x, stdevs_y, linestyle="none", marker=".", markersize=6, color='black')
        pl.xlabel("Iteration")
        pl.ylabel("Standard Deviation [mmag]")
        pl.savefig(f"{self.output_dirs['auxiliary']}/stdevs.png")
        pl.clf()

        # ================= PG PLOTS ===================
        # regular ======================================
        self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.lsamp, label="Data")
        self.add_pg_formatting_to_curfig()
        pl.savefig(f"{self.output_dirs['pgs_base']}/pg{n}_final_residual.png")
        pl.clf()
        # slf ==========================================
        if c_pg.slf_p is not None:
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.lsamp, label="Data")
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.get_slf_model(c_pg.lsfreq), color="red", label="SLF Fit")
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.get_slf_model(c_pg.lsfreq) * config.cutoff_sig,
                         color="blue", label="Minimum Selection Amplitude", linestyle="--")
            self.add_pg_formatting_to_curfig(legend=True)
            pl.savefig(f"{self.output_dirs['lcs_slf']}/pg{n}_final_residual.png")
            pl.clf()
        # lopoly =======================================
        if c_pg.polyparams_log is not None:
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.lsamp, label="Data")
            self.add_pg_plot_to_curfig(x=c_pg.lsfreq, y=c_pg.get_polyfit_model(c_pg.lsfreq), color="red", label="LOPoly Fit")
            self.add_pg_formatting_to_curfig(legend=True)
            pl.savefig(f"{self.output_dirs['lcs_lopoly']}/pg{n}_final_residual.png")
            pl.clf()

        self.save_freqs(freqs, f"{self.output_dirs['base']}/pwfrequencies.csv")
        # save last LC and PG to main dir
        self.add_lc_plot_to_curfig(lcs[-1].time, lcs[-1].data)
        self.add_lc_formatting_to_curfig()
        pl.savefig(f"{self.output_dirs['base']}/pw_residual_lc.png")
        pl.clf()

        self.add_pg_plot_to_curfig(lcs[-1].periodogram.lsfreq, lcs[-1].periodogram.lsamp)
        self.add_pg_formatting_to_curfig()
        pl.savefig(f"{self.output_dirs['base']}/residual_pg.png")
        pl.clf()
        self.save_freqs_as_latex_table(freqs, f"{self.main_dir}/freqtable.tex")

    def add_lc_plot_to_curfig(self, x, y, color="black", marker=".", alpha=1.0, linestyle="none", label="",
                              markersize=1):
        """
        Add a single light curve to the current plot. Passes through color, marker, alpha, linestyle, label,
        and markersize to pl.plot. Does not show or save the plot.
        """
        if self.cfg["output"]["plot_output_in_mmag"]:
            pl.plot(x, flux2mag(y, self.cfg["output"]["reference_flux"], self.cfg["output"]["reference_mag"]) * 1000,
                    color=color, marker=marker, alpha=alpha, linestyle=linestyle, label=label, markersize=markersize)
        else:
            pl.plot(x, y,
                    color=color, marker=marker, alpha=alpha, linestyle=linestyle, label=label, markersize=markersize)

    def add_lc_formatting_to_curfig(self, legend=False):
        """
        Adds formatting for a light curve to the current plot.
        :param bool legend: If true, add a legend
        :return: None
        """
        pl.xlabel(self.cfg["output"]["fig_labels"]["lc_x_label"])
        pl.ylabel(self.cfg["output"]["fig_labels"]["lc_x_label"])
        if legend:
            pl.legend()
        pl.tight_layout()

    def add_pg_plot_to_curfig(self, x, y, color="black", alpha=1.0, label="", linestyle="-"):
        """
        Adds a single periodogram to the current plot. Passes through color, alpha, label, and linestyle to pl.plot().
        Does not show or save the plot.
        """
        if self.cfg["output"]["plot_output_in_mmag"]:
            pl.plot(x, flux2mag(y, self.cfg["output"]["reference_flux"], self.cfg["output"]["reference_mag"]) * 1000,
                    color=color, alpha=alpha, label=label, linestyle=linestyle)
        else:
            pl.plot(x, y,
                    color=color, alpha=alpha, label=label, linestyle=linestyle)

    def add_pg_formatting_to_curfig(self, legend=False):
        """
        Adds formatting for a periodogram to the current plot.
        :param bool legend: If true, add a legend
        :return: None
        """
        pl.xlabel(self.cfg["output"]["fig_labels"]["pg_x_label"])
        pl.ylabel(self.cfg["output"]["fig_labels"]["pg_x_label"])
        if legend:
            pl.legend()
        pl.tight_layout()

    def get_freq_params_in_mmag(self, freq):
        """
        Get the amplitude in mmag for a frequency with its amplitude measured in flux, and the appropriately-adjusted
        phase. The conversion to magnitude flips the shape of the variability component described by the freq object,
        therefore this multiplies the amplitude in magnitude by -1 and adjusts the phase appropriately.
        :param freq: A frequency object
        :return: Amplitude in mmag, amplitude uncertainty in mmag, adjusted phase, adjusted initial magnitude in mmag
        """
        a, a_err, p, a0, p0 = freq.a, freq.a_err, freq.p, freq.a0, freq.p0
        am, a_errm = flux2mag_e(a, self.cfg["output"]["reference_flux"], self.cfg["output"]["reference_mag"], a_err)
        a0m = flux2mag(a0, self.cfg["output"]["reference_flux"], self.cfg["output"]["reference_mag"])
        # flip so it's positive
        am *= -1
        # adjust phase appropriately
        pm = p - 0.5
        p0m = p0 - 0.5
        if pm < 0:
            pm += 1
        if p0m < 0:
            p0m += 1
        return am * 1000, a_errm * 1000, pm, a0m * 1000

    def save_freqs(self, freqs: FrequencyContainer, path: str):
        """
        Format and save a frequency list as a csv
        :param freqs: A list of Freq objects to save
        :param path: The path at which to save the data
        :return: None
        """
        with open(path, "w") as f:
            f.write(f"Freq,Amp,Phase,Freq_err,Amp_err,Phase_err,Sig_slf,Sig_lopoly,Sig_avg\n")
            if self.cfg["output"]["plot_output_in_mmag"]:
                for freq in freqs.get_flist():
                    am, a_errm, pm, _ = self.get_freq_params_in_mmag(freq)
                    f.write(
                        f"{freq.f},{am},{pm},{freq.f_err},{a_errm},{freq.p_err},{freq.sig_slf},{freq.sig_poly},{freq.sig_avg}\n")
            else:
                for freq in freqs.get_flist():
                    f.write(
                        f"{freq.f},{freq.a},{freq.m},{freq.f_err},{freq.a_err},{freq.p_err},{freq.sig_slf},"
                        f"{freq.sig_poly},{freq.sig_avg}\n")

    def save_freqs_as_latex_table(self, freqs: FrequencyContainer, path: str):
        """
        Format and save a frequency list as a latex table
        :param freqs: A list of Freq objects to save
        :param path: The path at which to save the data
        :return: None
        """
        with open(path, "w") as f:
            for freq in freqs.get_flist():
                am, a_errm, pm, _ = self.get_freq_params_in_mmag(freq)

                f.write(f"{freq.n + 1} & {format_output(freq.f, freq.f_err, 2)} & {format_output(am, a_errm, 2)} &"
                        f" {format_output(pm, freq.p_err, 2)} & {round(freq.sig_slf, 2)} & {round(freq.sig_avg, 2)} &"
                        f"\\\\ \n")

    def save_lc(self, lightcurve, path):
        """
        Save a Lightcurve object at the specified path as a space-delimited 3-column file
        """
        np.savetxt(path, X=np.transpose([lightcurve.time, lightcurve.data, lightcurve.err]), delimiter=" ")

    def save_pg(self, periodogram, path):
        """
        Save a Periodogram object at the specified path as a space-delimited 2-column file
        """
        np.savetxt(path, X=np.transpose([periodogram.lsfreq, periodogram.lsamp]), delimiter=" ")

<img src="thumbnail.png" alt="thumbnail" width="300"/>

# Cloud Regime Cookbook

[![nightly-build](https://github.com/ProjectPythia/cookbook-template/actions/workflows/nightly-build.yaml/badge.svg)](https://github.com/ProjectPythia/cookbook-template/actions/workflows/nightly-build.yaml)
[![Binder](https://binder.projectpythia.org/badge_logo.svg)](https://binder.projectpythia.org/v2/gh/Isaaciwd/Cloud-Regime-Cookbook/main?labpath=notebooks)

This Project Pythia Cookbook covers creating and analyzing Cloud Regimes   

## Motivation

The purpose of this cookbook is to lower the barrier to entry of Cloud Regime (CR) analysis. It will give the user the tools and instruction to create a set of Cloud regimes from their own data using k-means clustering with either wasserstein or euclidean distance. It walks the user through deciding on the number of cloud regimes to create, testing if their k-means setup is robust, creates maps of the resultant CRs, and shows the user how to investigate any variable they might wish in association with the occurrence of the CRs.  

## Authors

[Isaac Davis](@first-author), [Brian Medeiros](@second-author)
<!-- ### Contributors
Add contributors when there are more than just Isaac and Brian
 -->

## Structure

This cookbook is organized into 4 sections: 
- Introduction
- Choosing a Value of k
- Testing Cluster Robustness / Repeatability of Results
- Mapping and Analyzing Cloud Regimes 

In addition, `Functions.py` provides a small library of functions that are used in the Notebooks.

### Introduction

An introduction to the concept of Cloud Regimes and how they are used.

### Choosing a Value of k

This section walks the user through deciding on a value of k, or the number of clusters/Cloud Regimes to create.

### Testing Cluster Robustness / Repeatability of Results

How to check that results are robust and repeatable.

### Mapping and Analyzing Cloud Regimes 

Now that the user has created a robust set of Cloud Regimes, we map them out and can preform further analysis. Briefly, these are:
| __function__  | __description__ | 
| ------------- | --------------- | 
| `open_and_process` | Open data, process into a matrix for clustering, cluster, and/or create cluster labels |
| `plot_hists` | Plot the cloud regime cluster centers |
| `plot_rfo` | Plot relative frequency of occurrence maps of the cloud regimes |
| `emd_means` | K-means algorithm that uses wasserstein distance |
| `euclidean_kmeans` | Conventional kmeans using sklearn |
| `precomputed_clusters` | Compute cluster labels from precomputed cluster centers with appropriate distance |
| `create_land_mask` | Create a one hot matrix where lat lon coordinates are over land using cartopy |
| `plot_hists_k_testing` | Plot histograms from k sensitivty testing |
| `histogram_cor` | Create correlation matricies between the cluster centers of all cloud regimes |
| `spatial_cor` | Create correlation matricies between the spatial distribution of all cloud regimes |
| `kp1_histogram_cor` | Create correlation matricies between the cluster centers of k and (k+1) CRs |

## Running the Notebooks

You can either run the notebook using [Binder](https://binder.projectpythia.org/) or on your local machine. Some features will not be available on the Binder. If you wish to use your own data, a GPU with euclidean k-means, or if you wish to use Wasserstein k-means it is best to run on a local machine.

### Running on Binder

The simplest way to interact with a Jupyter Notebook is through
[Binder](https://binder.projectpythia.org/), which enables the execution of a
[Jupyter Book](https://jupyterbook.org) in the cloud. The details of how this works are not
important for now. All you need to know is how to launch a Pythia
Cookbooks chapter via Binder. Simply navigate your mouse to
the top right corner of the book chapter you are viewing and click
on the rocket ship icon, (see figure below), and be sure to select
“launch Binder”. After a moment you should be presented with a
notebook that you can interact with. I.e. you’ll be able to execute
and even change the example programs. You’ll see that the code cells
have no output at first, until you execute them by pressing
{kbd}`Shift`\+{kbd}`Enter`. Complete details on how to interact with
a live Jupyter notebook are described in [Getting Started with
Jupyter](https://foundations.projectpythia.org/foundations/getting-started-jupyter.html).

### Running on Your Own Machine

If you are interested in running this material locally on your computer, you will need to follow this workflow:

(Replace "cookbook-example" with the title of your cookbooks)

1. Clone the `https://github.com/Isaaciwd/Cloud-Regime-Cookbook` repository:

   ```bash
    git clone git@github.com:Isaaciwd/Cloud-Regime-Cookbook.git
   ```

2. Move into the `Cloud-Regime-Cookbook` directory
   ```bash
   cd Cloud-Regime-Cookbook
   ```
3. Create and activate your conda environment from the `environment.yml` file
   ```bash
   conda env create -f environment.yml
   conda activate cookbook-dev
   ```
4. Move into the `notebooks` directory and start up Jupyterlab
   ```bash
   cd notebooks/
   jupyter lab
   ```

<img src="thumbnail.png" alt="thumbnail" width="300"/>

# Cloud Regime Cookbook

[![nightly-build](https://github.com/ProjectPythia/cookbook-template/actions/workflows/nightly-build.yaml/badge.svg)](https://github.com/ProjectPythia/cookbook-template/actions/workflows/nightly-build.yaml)
[![Binder](https://binder.projectpythia.org/badge_logo.svg)](https://binder.projectpythia.org/v2/gh/Isaaciwd/Cloud-Regime-Cookbook/main?labpath=notebooks)

This Project Pythia Cookbook covers creating and analyzing Cloud Regimes   

## Motivation

The purpose of this cookbook is to lower the barrier to entry of Cloud Regime analysis. It will give the user the tools and instruction to create a set of Cloud regimes from their own data using k-means clustering with either wasserstein or euclidean distance. It walks the user through deciding on the number of cloud regimes to create, testing if their k-means setup is robust, and then creates maps of the resultant Cloud regimes.  

## Authors

[Isaac Davis](@first-author), [Brian Medeiros](@second-author)
### Contributors

<a href="https://github.com/ProjectPythia/cookbook-template/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ProjectPythia/cookbook-template" />
</a>

## Structure

This cookbook is broken up into 4 main sections - Introduction, Choosing a Value of k, Testing Cluster Robustness / Repeatability of Results, and Mapping and Analyzing Cloud Regimes 


### Introduction

An introduction to the concept of Cloud Regimes and how they are used.

### Choosing a Value of k

This section walks the user through deciding on a value of k, or the number of clusters/Cloud Regimes to create.

### Testing Cluster Robustness / Repeatability of Results

How to check that results are robust and repeatable.

### Mapping and Analyzing Cloud Regimes 

Now that the user has created a robust set of Cloud Regimes, we map them out and can preform further analysis.

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

1. Clone the `https://github.com/ProjectPythia/cookbook-example` repository:

   ```bash
    git clone https://github.com/ProjectPythia/cookbook-example.git
   ```

1. Move into the `cookbook-example` directory
   ```bash
   cd cookbook-example
   ```
1. Create and activate your conda environment from the `environment.yml` file
   ```bash
   conda env create -f environment.yml
   conda activate cookbook-example
   ```
1. Move into the `notebooks` directory and start up Jupyterlab
   ```bash
   cd notebooks/
   jupyter lab
   ```

#%%
import logging as lgr
# Silencing matplotlib and numba logs
lgr.getLogger('matplotlib').setLevel(lgr.WARNING)
lgr.getLogger('numba').setLevel(lgr.WARNING)
from time import perf_counter
import numpy as np
try : import wasserstein
except: 
    print('Wasserstein package is not installed so wasserstein distance cannot be used. Attempting to use wassertein distance will raise an error.')
    print('To use wasserstein distance please install the wasserstein package in your environment: https://pypi.org/project/Wasserstein/ ')
    print()
import matplotlib.pyplot as plt
from scipy import sparse
import xarray as xr
import matplotlib as mpl
from numba import njit
from sklearn.cluster import KMeans
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import cartopy.crs as ccrs
import cartopy
import glob
from math import ceil
from shapely.geometry import Point
from shapely.prepared import prep
import dask
#%%
# Avoid creation of large chunks with dask
dask.config.set({"array.slicing.split_large_chunks": False})

# Open data, process into an (n_observation, n_dims) matrix for clustering, cluster and or create cluster labels, and return them
def open_and_process(data_path, k, tol, max_iter, init, n_init, var_name, tau_var_name, ht_var_name, lat_var_name, lon_var_name, height_or_pressure, wasserstein_or_euclidean = "euclidean", premade_cloud_regimes=None, lat_range=None, lon_range=None, time_range=None, only_ocean_or_land=False, land_frac_var_name=None, cluster=True, gpu=False):
    # Getting files
    files = glob.glob(data_path)
    # Opening an initial dataset
    init_ds = xr.open_mfdataset(files[0])
    # Creating a list of all the variables in the dataset
    remove = list(init_ds.keys())
    # Deleting the variables we want to keep in our dataset, all remaining variables will be dropped upon opening the files, this allows for faster opening of large files
    remove.remove(var_name)
    # If land_frac_var_name is a string, take it out of the variables to be dropped upon opening files. If it has been entered incorrectly inform the user and proceed with TODO
    if land_frac_var_name != None:
        try: remove.remove(land_frac_var_name)
        except: 
            land_frac_var_name = None
            print(f'{land_frac_var_name} variable does not exist, make sure land_frac_var_name is set correctly. Using TODO for land mask')

    # Opening data
    lgr.info(' Opening dataset:')
    ds = xr.open_mfdataset(files, drop_variables = remove)

    # Turning into a dataarray
    lgr.info(' Opening finished. Beginning preprocessing:')
    ds = ds[var_name]

    # Adjusting lon to run from -180 to 180 if it doesnt already
    if np.max(ds.lon) > 180: 
        ds.coords['lon'] = (ds.coords['lon'] + 180) % 360 - 180
        ds = ds.sortby(ds.lon)

    # TODO MODIS has bogus values for pressure and tau in the coordinate variables, true values are listed as an attribute. This slice of code is still compatible with modis, but may not be compatible with another dataset that stores bogus coordinate values
    # Reordering y dimension from lowest to graound to highest if it needs to be reordered
    if height_or_pressure == 'h': 
        if ds[ht_var_name][0] > ds[ht_var_name][-1]: 
            ds.reindex({ht_var_name:ds[ht_var_name][::-1]})
    if height_or_pressure == 'p':
        if ds[ht_var_name][0] < ds[ht_var_name][-1]: 
            ds.reindex({ht_var_name:ds[ht_var_name][::-1]})

    # Selecting only points over ocean or points over land if only_ocean_or_land has been used
    if only_ocean_or_land != False:

        # Mask out land or water with LANDFRAC variable if we have it
        if land_frac_var_name != None:
            if only_ocean_or_land == 'L': ds = ds.where(ds[land_frac_var_name] == 1)
            elif only_ocean_or_land == 'O': ds = ds.where(ds[land_frac_var_name] == 0)
            else: raise Exception('Invalid option for only_ocean_or_land: Please enter "O" for ocean only, "L" for land only, or set to False for both land and water')

        # Otherwise use cartopy
        else:
            # Creating land mask
            oh_land = create_land_mask(ds)

            # inserting new axis to make oh_land a broadcastable shape with ds
            dims = ds.dims
            for n in range(len(dims)):
                if dims[n] != lat_var_name and dims[n] != lon_var_name:
                    oh_land = np.expand_dims(oh_land, n)

            # Masking out the land or water
            if only_ocean_or_land == 'L': ds = ds.where(oh_land == 1)
            elif only_ocean_or_land == 'O': ds = ds.where(oh_land == 0)
            else: raise Exception('Invalid option for only_ocean_or_land: Please enter "O" for ocean only, "L" for land only, or set to False for both land and water')
        
    # Selecting lat range
    if lat_range is not None:
        lat_selection = {lat_var_name:slice(np.min(lat_range),np.max(lat_range))}
        ds = ds.sel(lat_selection)
    # if lat_range != None:
    #     if ds[lat_var_name][0] > ds[lat_var_name][-1]:
    #         lat_selection = {lat_var_name:slice(lat_range[1],lat_range[0])}
    #         ds = ds.sel(lat_selection)
    #     else:
    #         lat_selection = {lat_var_name:slice(lat_range[0],lat_range[1])}
    #         ds = ds.sel(lat_selection)

    # Selecting Lon range
    if lon_range is not None:
        lon_selection = {lon_var_name:slice(np.min(lon_range),np.max(lon_range))}
        ds = ds.sel(lon_selection)
    # if lon_range != None:
    #     if ds[lon_var_name][0] > ds[lon_var_name][-1]:
    #         lon_selection = {lon_var_name:slice(lon_range[1],lon_range[0])}
    #         ds = ds.sel(lon_selection)
    #     else:
    #         lon_selection = {lon_var_name:slice(lon_range[0],lon_range[1])}
    #         ds = ds.sel(lon_selection)

    # Selecting time range
    if time_range != None:
        ds = ds.sel(time=slice(time_range[0],time_range[1]))

    # Selecting only valid tau and height/pressure range
    # Many data products have a -1 bin for failed retreivals, we do not wish to include this
    tau_selection = {tau_var_name:slice(0,None)}
    # Making sure this works for pressure which is ordered largest to smallest and altitude which is ordered smallest to largest
    if ds[ht_var_name][0] > ds[ht_var_name][-1]: ht_selection = {ht_var_name:slice(None,0)}
    else: ht_selection = {ht_var_name:slice(0,None)}
    ds = ds.sel(tau_selection)
    ds = ds.sel(ht_selection)

    # Selcting only the relevant data and stacking it to shape n_histograms, n_tau * n_pc
    lgr.info(' Reshaping data to shape (n_histograms, n_tau_bins* n_pc_bins):')
    dims = list(ds.dims)
    dims.remove(tau_var_name)
    dims.remove(ht_var_name)
    histograms = ds.stack(spacetime=(dims), tau_ht=(tau_var_name, ht_var_name))
    weights = np.cos(np.deg2rad(histograms[lat_var_name].values)) # weights array to use with emd-kmeans

    # Turning into a numpy array for clustering
    lgr.info(' Reading data into memory:')
    mat = histograms.values

    # Removing all histograms with 1 or more nans in them
    indicies = np.arange(len(mat))
    is_valid = ~np.isnan(mat.mean(axis=1))
    is_valid = is_valid.astype(np.int32)
    valid_indicies = indicies[is_valid==1]
    mat=mat[valid_indicies]
    weights=weights[valid_indicies]

    # Safetey check that shouldnt really be necesary
    if np.any(mat < 0):
        raise Exception (f'Found negative value in ds.{var_name}, if this is a fill value for missing data, convert to nans and try again')
    
    # If cluster is not true, then skip clustering and just return the oopened and preprocessed data
    lgr.info(' Finished preprocessing:')

    if cluster == False:
        return mat, valid_indicies, ds, histograms, weights
    
    # If the function call sepecifies to cluster/calcuate cluster labels, then do it
    else:
        # Use premade clusters to calculate cluster labels (using specified distance metric) if they have been provided
        if isinstance(premade_cloud_regimes, str):
            lgr.info(' Calculating cluster_labels for premade_cloud_regimes:')
            s = perf_counter()
            try: cl = np.load(premade_cloud_regimes)
            except: cl = xr.open_datarray(premade_cloud_regimes).values
            k = len(cl)
            if cl.shape != (k,len(ds[tau_var_name]) * len(ds[ht_var_name])):
                raise Exception (f"""premade_cloud_regimes is the wrong shape. premade_cloud_regimes.shape = {cl.shape}, but must be shape {(k,len(ds.tau_var_name) * len(ds.ht_var_name))} 
                to fit the loaded data. This shape mismatch often happens when fitting model data into CRs made from observation. Many of the satellite simulators include extra tau or cloud top pressure/height 
                bins that do not exist in the observation data: you may need to sum these extra bins together to remove them. Additionally, some observation datasets
                have additional tau or height/pressure bins (often labeled with values of -1) to indicate failed retrievals. It is important to trim off these extra bins before creating CRs
                or fitting into CRs made by other data.""")
            cluster_labels_temp = precomputed_clusters(mat, cl, wasserstein_or_euclidean, ds, tau_var_name, ht_var_name)
            lgr.info(f' {round(perf_counter()-s)} seconds to calculate cluster_labels for premade_cloud_regimes:')
            
        # Otherwise preform clustering with specified distance metric
        else:
            lgr.info(' Beginning clustering:')
            s = perf_counter()
            if wasserstein_or_euclidean == "wasserstein":
                cl, cluster_labels_temp, il, cl_list = emd_means(mat, k, tol, init, n_init, ds, tau_var_name, ht_var_name, max_iter, weights = None)
            elif wasserstein_or_euclidean == "euclidean":
                cl, cluster_labels_temp = euclidean_kmeans(k, init, n_init, mat, max_iter, tol, gpu)
            else: raise Exception ('Invalid option for wasserstein_or_euclidean. Please enter "wasserstein", "euclidean", or a numpy ndarray to use as premade cloud regimes and preform no clustering')
            lgr.info(f' {round(perf_counter()-s)} seconds to cluster:')

        # Taking the flattened cluster_labels_temp array, and turning it into a datarray the shape of ds.var_name, and reinserting NaNs in place of missing data
        cluster_labels = np.full(len(indicies), np.nan, dtype=np.int32)
        cluster_labels[valid_indicies]=cluster_labels_temp
        cluster_labels = xr.DataArray(data=cluster_labels, coords={"spacetime":histograms.spacetime},dims=("spacetime") )
        cluster_labels = cluster_labels.unstack()
        return mat, cluster_labels, cluster_labels_temp, valid_indicies, ds

# Plot the CR cluster centers
def plot_hists(cluster_labels, k, ds, ht_var_name, tau_var_name, valid_indicies, mat, cluster_labels_temp, height_or_pressure, save_path):

    # setting up plots
    ylabels = ds[ht_var_name].values
    xlabels = ds[tau_var_name].values
    X2,Y2 = np.meshgrid(np.arange(len(xlabels)+1), np.arange(len(ylabels)+1))
    p = [0,0.2,1,2,3,4,6,8,10,15,99]
    cmap = mpl.colors.ListedColormap(['white', (0.19215686274509805, 0.25098039215686274, 0.5607843137254902), (0.23529411764705882, 0.3333333333333333, 0.6313725490196078), (0.32941176470588235, 0.5098039215686274, 0.6980392156862745), (0.39215686274509803, 0.6, 0.43137254901960786), (0.44313725490196076, 0.6588235294117647, 0.21568627450980393), (0.4980392156862745, 0.6784313725490196, 0.1843137254901961), (0.5725490196078431, 0.7137254901960784, 0.16862745098039217), (0.7529411764705882, 0.8117647058823529, 0.2), (0.9568627450980393, 0.8980392156862745,0.1607843137254902)])
    norm = mpl.colors.BoundaryNorm(p,cmap.N)
    plt.rcParams.update({'font.size': 12})
    fig_height = 1 + 10/3 * ceil(k/3)
    fig, ax = plt.subplots(figsize = (17, fig_height), ncols=3, nrows=ceil(k/3), sharex='all', sharey = True)

    aa = ax.ravel()
    boundaries = p
    norm = mpl.colors.BoundaryNorm(boundaries, cmap.N, clip=True)
    aa[1].invert_yaxis()

    # creating weights area for area weighted RFOs
    weights = cluster_labels.stack(z=('time','lat','lon')).lat.values
    weights = np.cos(np.deg2rad(weights))
    weights = weights[valid_indicies]
    indicies = np.arange(len(mat))

    # Plotting each cluster center
    for i in range (k):

        # Area Weighted relative Frequency of occurence calculation
        total_rfo_num = cluster_labels == i 
        total_rfo_num = np.sum(total_rfo_num * np.cos(np.deg2rad(cluster_labels.lat)))
        total_rfo_denom = cluster_labels >= 0
        total_rfo_denom = np.sum(total_rfo_denom * np.cos(np.deg2rad(cluster_labels.lat)))
        total_rfo = total_rfo_num  / total_rfo_denom * 100
        total_rfo = total_rfo.values

        # Area weighting each histogram belonging to a cluster and taking the mean
        # if clustering was preformed with wasserstein distance and area weighting on, mean of i = cl[i], however if clustering was preformed with
        # conventional kmeans or wasseerstein without weighting, these two will not be equal
        indicies_i = indicies[np.where(cluster_labels_temp == i)]
        mean = mat[indicies_i] * weights[indicies_i][:,np.newaxis]
        mean = np.sum(mean, axis=0) / np.sum(weights[indicies_i])
        mean = mean.reshape(len(xlabels),len(ylabels)).T           # reshaping into original histogram shape
        if np.max(mean) <= 1:                                      # Converting fractional data to percent to plot properly
            mean *= 100

        im = aa[i].pcolormesh(X2,Y2,mean,norm=norm,cmap=cmap)
        aa[i].set_title(f"CR {i+1}, RFO = {np.round(total_rfo,1)}%")

    # setting titles, labels, etc
    if height_or_pressure == 'p': fig.supylabel(f'Cloud-top Pressure', fontsize = 12, x = 0.09 )
    if height_or_pressure == 'h': fig.supylabel(f'Cloud-top Height', fontsize = 12, x = 0.09  )
    # fig.supxlabel('Optical Depth', fontsize = 12, y=0.26 )
    cbar_ax = fig.add_axes([0.95, 0.38, 0.045, 0.45])
    cb = fig.colorbar(im, cax=cbar_ax, ticks=p)
    cb.set_label(label='Cloud Cover (%)', size =10)
    cb.ax.tick_params(labelsize=9)
    #aa[6].set_position([0.399, 0.125, 0.228, 0.215])
    #aa[6].set_position([0.33, 0.117, 0.36, 0.16])
    #aa[-2].remove()

    bbox = aa[1].get_position()
    p1 = bbox.p1
    p0 = bbox.p0
    fig.suptitle(f'Cloud Regimes', x=0.5, y=p1[1]+(1/fig_height * 0.5), fontsize=15)

    bbox = aa[-2].get_position()
    p1 = bbox.p1
    p0 = bbox.p0
    fig.supxlabel('Optical Depth', fontsize = 12, y=p0[1]-(1/fig_height * 0.5) )


    # Removing extra plots
    for i in range(ceil(k/3)*3-k):
        aa[-(i+1)].remove()

    if save_path != None:
        plt.savefig(save_path + 'cluster_centers.png')

    plt.show()
    plt.close()

    #TODO why is this here?
    return mat, cluster_labels, cluster_labels_temp, valid_indicies, ds

# Plot RFO maps of the CRss
def plot_rfo(cluster_labels, k ,ds, save_path):
    
    COLOR = 'black'
    mpl.rcParams['text.color'] = COLOR
    mpl.rcParams['axes.labelcolor'] = COLOR
    mpl.rcParams['xtick.color'] = COLOR
    mpl.rcParams['ytick.color'] = COLOR
    plt.rcParams.update({'font.size': 10})
    plt.rcParams['figure.dpi'] = 150
    fig_height = 2.2 * ceil(k/2)
    fig, ax = plt.subplots(ncols=2, nrows=int(k/2 + k%2), subplot_kw={'projection': ccrs.PlateCarree()}, figsize = (10,fig_height))#, sharex='col', sharey='row')
    plt.subplots_adjust(wspace=0.13, hspace=0.05)
    aa = ax.ravel()

    X, Y = np. meshgrid(ds.lon,ds.lat)

    # Plotting the rfo of each cluster
    tot_rfo_sum = 0 
    
    for cluster in range(k): #range(0,k+1):
        # Calculating rfo
        rfo = np.sum(cluster_labels==cluster, axis=0) / np.sum(cluster_labels >= 0, axis=0) * 100
        # tca_explained = np.sum(cluster_labels == cluster) * np.sum(init_clusters[cluster]) / total_cloud_amnt * 100
        # tca_explained = round(float(tca_explained.values),1)
        aa[cluster].set_extent([-180, 180, -90, 90])
        aa[cluster].coastlines()
        mesh = aa[cluster].pcolormesh(X, Y, rfo, transform=ccrs.PlateCarree(), rasterized = True, cmap="GnBu",vmin=0,vmax=100)
        #total_rfo = np.sum(cluster_labels==cluster) / np.sum(cluster_labels >= 0) * 100
        # total_rfo_num = np.sum(cluster_labels == cluster * np.cos(np.deg2rad(cluster_labels.lat)))
        total_rfo_num = cluster_labels == cluster 
        total_rfo_num = np.sum(total_rfo_num * np.cos(np.deg2rad(cluster_labels.lat)))
        total_rfo_denom = cluster_labels >= 0
        total_rfo_denom = np.sum(total_rfo_denom * np.cos(np.deg2rad(cluster_labels.lat)))

        total_rfo = total_rfo_num  / total_rfo_denom * 100
        tot_rfo_sum += total_rfo
        aa[cluster].set_title(f"CR {cluster+1}, RFO = {round(float(total_rfo),1)}", pad=4)
        # aa[cluster].gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
        # x_label_plot_list = [4,5,6]
        # y_label_plot_list = [0,2,4,6]
        # if cluster in x_label_plot_list:


        if cluster % 2 == 0:
            aa[cluster].set_yticks([-60,-30,0,30,60], crs=ccrs.PlateCarree())        
            lat_formatter = LatitudeFormatter()
            aa[cluster].yaxis.set_major_formatter(lat_formatter)

    #aa[7].set_title(f"Weathersdfasdfa State {i+1}, RFO = {round(float(total_rfo),1)}", pad=-40)
    cb = plt.colorbar(mesh, ax = ax, anchor =(-0.28,0.83), shrink = 0.6)
    cb.set_label(label = 'RFO (%)', labelpad=-3)

    x_ticks_indicies = np.array([-1,-2])

    if k%2 == 1:
        aa[-1].remove()
        x_ticks_indicies -= 1

        #aa[-2].set_position([0.27, 0.11, 0.31, 0.15])

    # plotting x labels on final two plots
    aa[x_ticks_indicies[0]].set_xticks([-120,-60,0,60,120,], crs=ccrs.PlateCarree())
    lon_formatter = LongitudeFormatter(zero_direction_label=True)
    aa[x_ticks_indicies[0]].xaxis.set_major_formatter(lon_formatter)
    aa[x_ticks_indicies[1]].set_xticks([-120,-60,0,60,120,], crs=ccrs.PlateCarree())
    lon_formatter = LongitudeFormatter(zero_direction_label=True)
    aa[x_ticks_indicies[1]].xaxis.set_major_formatter(lon_formatter)

    bbox = aa[1].get_position()
    p1 = bbox.p1
    plt.suptitle(f"CR Relative Frequency of Occurence", x= 0.43, y= p1[1]+(1/fig_height * 0.5))#, {round(cl[cluster,23],4)}")
    
    if save_path != None:
        plt.savefig(save_path + 'rfo_maps.png')

    plt.show()
    plt.close()


# K-means algorithm that uses wasserstein distance
def emd_means(mat, k, tol, init, n_init, ds, tau_var_name, ht_var_name, hard_stop = 45, weights = None):

    # A function to convert mat into the form reqired by the wasserstein package
    @njit()
    def stacking(position_matrix, centroids):
        centroid_list = []

        for i in range(len(centroids)):
            x = np.empty((3,len(mat[0]))).T
            x[:,0] = centroids[i]
            x[:,1] = position_matrix[0]
            x[:,2] = position_matrix[1]
            centroid_list.append(x)

        return centroid_list

    n, d = mat.shape

    # checking for a weights array to prefrom a weighted kmeans with
    if type(weights) == np.ndarray: 
        weighted = True
        mat_w = mat * weights[:,None]
    else: weighted = False

    centroid_labels = np.arange(k, dtype=np.int32)  # (k, )
  
    centroid_tracking = []
    inertia_tracking = np.zeros(n_init)

    # Setting the number of tau and height dimensions for each data set
    n1 = len(ds[tau_var_name])
    n2 = len(ds[ht_var_name])

    # Calculating the max distance between two points to be used as hyperparameter in EMD
    # This is not necesarily the only value for this variable that can be used, see Wasserstein documentation
    # on R hyper-parameter for more information
    R = (n1**2+n2**2)**0.5

    # Creating a flattened position matrix to pass wasersstein.PairwiseEMD
    position_matrix = np.zeros((2,n1,n2))
    position_matrix[0] = np.tile(np.arange(n2),(n1,1))
    position_matrix[1] = np.tile(np.arange(n1),(n2,1)).T
    position_matrix = position_matrix.reshape(2,-1)

    # Initialising wasserstein.PairwiseEMD
    emds = wasserstein.PairwiseEMD(R = R, norm=True, dtype=np.float32, verbose=0, num_threads=162)

    # Rearranging mat to be in the format necesary for wasserstein.PairwiseEMD
    events = stacking(position_matrix, mat)

    # Preforming n_init initiations of the kmeans algorithm, and then keeping the best initiation as a result
    for init_number in range(n_init):
        emd_inertia_list = []

        # Using Kmeans++ if init  == True
        if init == 'k-means++':
            init_clusters = np.zeros((k, len(mat[0])))
            init_clusters[0] = mat[np.random.randint(0,len(mat))]
            centroid_list = stacking(position_matrix, init_clusters)

            dists_ar = np.full((len(mat),k-1), np.inf)
            x = perf_counter()
            for i in range(k-1):
                emds(events,centroid_list[i:i+1])
                dists_ar[:,i] = emds.emds().squeeze()
                weights_kpp = np.min(dists_ar, axis=1)
                weights_kpp = weights_kpp / np.sum(weights_kpp)

                choice = np.random.choice(np.arange(len(mat)), 1, p=weights_kpp)
                init_clusters[i+1] = mat[choice]
                centroid_list = stacking(position_matrix, init_clusters)

            lgr.info(f" {round(perf_counter()-x,1)} Seconds for k-means++ initialization:")

            centroids = init_clusters
        
        # Using array entered as init as initial centroids if init is an ndarray
        elif type(init) == np.ndarray:
            if init.shape != (k,d): raise Exception ('init array must be shape (k, n_tau_bins * n_pressure_bins)')
            centroids = init
            n_init = 1 # Doing more than one init in this case is useless, as they will all have the same result
        
        # Otherwise using random initiation
        elif init == 'random':
            # Randomly picking k observations to use as initial clusters
            centroids = mat[np.random.choice(n, k, replace=False)]  # (k, d)

        else:
            raise Exception (f'Enter valid option for init. Enter "k-means++" to use kmeans++, "random" for random initiation, or set equal to a (k, n_tau_bins * n_pressure_bins) shaped ndarray to use as initial clusters. You entered {init}')

        iter = 0

        # initializing inertia_diff so loop will run, true values is calculated after the second iteration
        inertia_diff = tol+1 
        t = 0
        while inertia_diff >= tol:

            # ASSIGNMENT STEP
            centroid_list = stacking(position_matrix, centroids)
            emds(events, centroid_list)
            distances = emds.emds()
            labels = np.argmin(distances, axis=1)

            #calculating emd_inertia
            onehot_matrix = labels[:,None] == centroid_labels  # (n, k)
            if weighted: emd_inertia = np.sum((distances[onehot_matrix]*weights/np.sum(weights))**2)
            else: emd_inertia = np.sum(distances[onehot_matrix]**2)
            emd_inertia_list.append(emd_inertia)
            
            # Updating cluster centroids
            if weighted == False:
                b_data, b_oh = np.broadcast_arrays(  # (n, k, d), (n, k, d)
                    mat[:, None], onehot_matrix[:, :, None])
                centroids =  b_data.mean(axis=0, where=b_oh)  # (k, d)
            
            # Updating cluster centers as area weighted average
            if weighted == True:
                centroids = np.zeros((k,d))
                for i in range (k):
                    centroids[i] = np.sum(mat_w[np.where(labels == i)], axis = 0) / np.sum(weights[np.where(labels == i)])

            # Calculate change in inertia from last step
            if iter > 0:
                inertia_diff = emd_inertia_list[-2] - emd_inertia_list[-1]
                lgr.info(f" Change in inertia from last iteration = {round(inertia_diff,1)}")

            iter += 1
        
            # Check if we've reached the hard stop on number of iterations
            if iter == hard_stop:
                lgr.warning(f" max_iter = {hard_stop} reached, this run may not have converged")
                lgr.info(f" tol = {tol}, final change in inertia = {round(inertia_diff,1)}, final inertia = {round(emd_inertia,1)}")
                break

        lgr.info(f" {iter} iterations until convergence with tol = {tol} ")

        centroid_tracking.append(centroids)
        inertia_tracking[init_number] = emd_inertia

        lgr.info(f" Finished initiation {init_number+1} out of {n_init} ")
        

    # retreiving the cluster centers that had the lowest inertia
    best_result = np.argmin(inertia_tracking)

    # recaluclating cluster labels to the final updated cluster centers
    centroid_list = stacking(position_matrix, centroids)
    emds(events, centroid_list)
    distances = emds.emds()
    labels = np.argmin(distances, axis=1)

    return centroid_tracking[best_result], labels, inertia_tracking, centroid_tracking

# Conventional kmeans using sklearn
def euclidean_kmeans(k, init, n_init, mat, max_iter, tol, gpu = False):
    if gpu == False:
        # Seting up kmeans nd fitting the data
        kmeans = KMeans(n_clusters=k, init = init, n_init = n_init, max_iter=max_iter+1, tol=tol).fit(mat)
        # Retreiving cluster labels
        cluster_labels_temp = kmeans.labels_
        # Retreiving cluster centers
        cl = kmeans.cluster_centers_

        # Checking for convergence
        if kmeans.n_iter_ == max_iter+1:
            raise Exception ('KMeans did not converge. Either tol is set too small, or max_iter is too small. Please change one and try again')
   
    # TODO: test this on GPU, does .n_iter_ work for CUML?
    if gpu == True:
        import cuml
        import cupy as cp

        # If user wants kmeans++, use cumls fast and parallelized GPU implimentation
        if init == "k-means++": init = 'k-means||'

        # Moving mat onto GPU
        gpu_mat = cp.asarray(mat)
        # Initializing kmeans
        kmeans=cuml.cluster.KMeans(n_clusters=k, max_iter=max_iter+1, init=init, tol= tol, n_init=n_init, output_type = "numpy")
        # Fitting data
        kmeans.fit(gpu_mat)
        # Retreiving cluster_centers and labels
        cl = kmeans.cluster_centers_
        cluster_labels_temp = kmeans.labels_

        # Checking for convergence
        if kmeans.n_iter_ == max_iter+1:
            raise Exception ('KMeans did not converge. Either tol is set too small, or max_iter is too small. Please change one and try again')
   
    return cl, cluster_labels_temp

# Compute cluster labels from precomputed cluster centers with appropriate distance
def precomputed_clusters(mat, cl, wasserstein_or_euclidean, ds, tau_var_name, ht_var_name):

    if wasserstein_or_euclidean == 'euclidean':
        cluster_dists = np.sum((mat[:,:,None] - cl.T[None,:,:])**2, axis = 1)
        cluster_labels_temp = np.argmin(cluster_dists, axis = 1)

    if wasserstein_or_euclidean == 'wasserstein':

        # A function to convert mat into the form required for the EMD calculation
        @njit()
        def stacking(position_matrix, centroids):
            centroid_list = []

            for i in range(len(centroids)):
                x = np.empty((3,len(mat[0]))).T
                x[:,0] = centroids[i]
                x[:,1] = position_matrix[0]
                x[:,2] = position_matrix[1]
                centroid_list.append(x)

            return centroid_list
        
        # setting shape
        n1 = len(ds[tau_var_name])
        n2 = len(ds[ht_var_name])

        # Calculating the max distance between two points to be used as hyperparameter in EMD
        # This is not necesarily the only value for this variable that can be used, see Wasserstein documentation
        # on R hyper-parameter for more information
        R = (n1**2+n2**2)**0.5

        # Creating a flattened position matrix to pass wasersstein.PairwiseEMD
        position_matrix = np.zeros((2,n1,n2))
        position_matrix[0] = np.tile(np.arange(n2),(n1,1))
        position_matrix[1] = np.tile(np.arange(n1),(n2,1)).T
        position_matrix = position_matrix.reshape(2,-1)

        # Initialising wasserstein.PairwiseEMD
        emds = wasserstein.PairwiseEMD(R = R, norm=True, dtype=np.float32, verbose=1, num_threads=162)

        # Rearranging mat to be in the format necesary for wasserstein.PairwiseEMD
        events = stacking(position_matrix, mat)
        centroid_list = stacking(position_matrix, cl)
        emds(events, centroid_list)
        distances = emds.emds()
        labels = np.argmin(distances, axis=1)

        cluster_labels_temp = np.argmin(distances, axis=1)
        
    return cluster_labels_temp

# Create a one hot matrix where lat lon coordinates are over land using cartopy
def create_land_mask(ds):
    
    land_110m = cartopy.feature.NaturalEarthFeature('physical', 'land', '110m')
    land_polygons = list(land_110m.geometries())
    land_polygons = [prep(land_polygon) for land_polygon in land_polygons]

    lats = ds.lat.values
    lons = ds.lon.values
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    points = [Point(point) for point in zip(lon_grid.ravel(), lat_grid.ravel())]

    land = []
    for land_polygon in land_polygons:
        land.extend([tuple(point.coords)[0] for point in filter(land_polygon.covers, points)])

    landar = np.asarray(land)
    lat_lon = np.empty((len(lats)*len(lons),2))
    oh_land = np.zeros((len(lats)*len(lons)))
    lat_lon[:,0] = lon_grid.flatten()
    lat_lon[:,1] = lat_grid.flatten()

    @njit()
    def test (oh_land, lat_lon, landar):
        for i in range(len(oh_land)):
            check = lat_lon[i] == landar
            if np.max(np.sum(check,axis=1)) == 2:
                oh_land[i] = 1
        return oh_land
    oh_land = test (oh_land, lat_lon, landar)


    oh_land=oh_land.reshape((len(lats),len(lons)))

    return oh_land

# Plot histograms from k_sensitivty_testing.py
def plot_hists_k_testing(histograms, k, ds, tau_var_name, ht_var_name, height_or_pressure, save_path):
    # Converting fractional data to percent to plot properly
    if np.max(histograms) <= 1:
        histograms *= 100

    # setting up plots
    ylabels = ds[ht_var_name].values
    xlabels = ds[tau_var_name].values
    X2,Y2 = np.meshgrid(np.arange(len(xlabels) + 1), np.arange(len(ylabels+1)))
    p = [0,0.2,1,2,3,4,6,8,10,15,99]
    cmap = mpl.colors.ListedColormap(['white', (0.19215686274509805, 0.25098039215686274, 0.5607843137254902), (0.23529411764705882, 0.3333333333333333, 0.6313725490196078), (0.32941176470588235, 0.5098039215686274, 0.6980392156862745), (0.39215686274509803, 0.6, 0.43137254901960786), (0.44313725490196076, 0.6588235294117647, 0.21568627450980393), (0.4980392156862745, 0.6784313725490196, 0.1843137254901961), (0.5725490196078431, 0.7137254901960784, 0.16862745098039217), (0.7529411764705882, 0.8117647058823529, 0.2), (0.9568627450980393, 0.8980392156862745,0.1607843137254902)])
    norm = mpl.colors.BoundaryNorm(p,cmap.N)
    plt.rcParams.update({'font.size': 12})
    n_histo = len(histograms)
    fig_height = 1 + 10/3 * ceil(n_histo/3)
    fig, ax = plt.subplots(figsize = (17, fig_height), ncols=3, nrows=ceil(n_histo/3), sharex='all', sharey = True)

    aa = ax.ravel()
    boundaries = p
    norm = mpl.colors.BoundaryNorm(boundaries, cmap.N, clip=True)
    aa[1].invert_yaxis()

    # Plotting each cluster center
    for i in range (n_histo):

        im = aa[i].pcolormesh(X2,Y2,histograms[i].reshape(len(xlabels),len(ylabels)).T ,norm=norm,cmap=cmap)
        # aa[i].set_title(f"CR {i+1}, RFO = {np.round(total_rfo,1)}%")

    # setting titles, labels, etc
    if height_or_pressure == 'p': fig.supylabel(f'Cloud-top Pressure', fontsize = 12, x = 0.09 )
    if height_or_pressure == 'h': fig.supylabel(f'Cloud-top Height', fontsize = 12, x = 0.09  )
    # fig.supxlabel('Optical Depth', fontsize = 12, y=0.26 )
    cbar_ax = fig.add_axes([0.95, 0.38, 0.045, 0.45])
    cb = fig.colorbar(im, cax=cbar_ax, ticks=p)
    cb.set_label(label='Cloud Cover (%)', size =10)
    cb.ax.tick_params(labelsize=9)
    #aa[6].set_position([0.399, 0.125, 0.228, 0.215])
    #aa[6].set_position([0.33, 0.117, 0.36, 0.16])
    #aa[-2].remove()

    bbox = aa[1].get_position()
    p1 = bbox.p1
    p0 = bbox.p0
    # fig.suptitle(f'{data} Cloud Regimes', x=0.5, y=p1[1]+(1/fig_height * 0.5), fontsize=15)

    bbox = aa[-2].get_position()
    p1 = bbox.p1
    p0 = bbox.p0
    fig.supxlabel('Optical Depth', fontsize = 12, y=p0[1]-(1/fig_height * 0.5) )


    # Removing extra plots
    if n_histo > 2:
        for i in range(ceil(k/3)*3-k):
            aa[-(i+1)].remove()

    if save_path != None:
        plt.savefig(save_path + f'{k}k_sensitivity_testing_histograms.png')

    plt.show()
    plt.close()


# Create correlation matricies between the cluster centers of all cloud regimes
def histogram_cor(cl, save_path):

    # Creating Correlation pcolormesh
    plt.figure(figsize=(8, 6), dpi=150)
    MxClusters = len(cl)
    cor_coefs = np.zeros((MxClusters,MxClusters))

    for i in range (MxClusters):
        for x in range (MxClusters):
            cor_coefs[i,x] = np.corrcoef(cl[i].flatten(),cl[x].flatten())[0,1]

    cmap = plt.cm.get_cmap('Spectral').reversed()

    im = plt.pcolormesh(cor_coefs, vmin = -1, vmax = 1, cmap = cmap)
    plt.colorbar(im)

    ticklabels = []
    for i in range(MxClusters):
        ticklabels.append(f'WS{i+1}')

    positions = np.arange(MxClusters)+0.2
    for i in range (MxClusters):
        for x in range (MxClusters):
            plt.text(positions[i],positions[x]+0.1, round(cor_coefs[i,x],2), color='k')

    plt.xticks(ticks = positions+0.3, labels = ticklabels)
    plt.yticks(ticks = positions+0.3, labels = ticklabels)

    plt.title(f"CR Histogram Correlation Matrices, K = {MxClusters}")
    #plt.savefig(f"/glade/work/idavis/isccp_clustering/monthly/k_correlation_testing/{MxClusters}C_correlation_matrix_{save_index}")

    # plt.clf()
    plt.show()

    # if np.max(cor_coefs[np.triu_indices(MxClusters, k=1)]) > 0.8:
    #     print(f'k = {MxClusters} failed the histogram correlation test. The maximum alowable correlation is 0.8, but the maximum correlation is {round(np.max(cor_coefs[np.triu_indices(MxClusters, k=1)]),2)}')
    
    if save_path != None:
        plt.savefig(save_path + f'{MxClusters}k_histogram_correlations.png')

    plt.show()
    plt.close()

# Create correlation matricies between the spatial distribution of all cloud regimes
def spatial_cor(cluster_labels_temp, k, save_path):

    # Making one hot array shape (k,num_observations) where the observation = a cluster
    all_rfo = np.zeros((k,len(cluster_labels_temp)))
    for cluster in range(0,k):
        all_rfo[cluster] = cluster_labels_temp == cluster

    # Masking out invalid values, accounts for differing fill values
    all_rfo = np.ma.masked_invalid(all_rfo)
    all_rfo = np.ma.masked_where(all_rfo<0, all_rfo)
    all_rfo = np.ma.masked_where(all_rfo>k-1, all_rfo)

    # Creating Correlation pcolormesh
    plt.figure(figsize=(8, 6), dpi=150)
    cor_coefs = np.zeros((k,k))
    for i in range (k):
        for x in range (k):
            cor_coefs[i,x] = np.ma.corrcoef(all_rfo[i],all_rfo[x])[0,1]

    # Setting up plot
    cmap = plt.cm.get_cmap('Spectral').reversed()
    im = plt.pcolormesh(cor_coefs, vmin = -1, vmax =1, cmap = cmap)
    plt.colorbar(im)

    ticklabels = []
    for i in range(k):
        ticklabels.append(f'WS{i+1}')

    positions = np.arange(k)+0.2
    for i in range (k):
        for x in range (k):
            plt.text(positions[i],positions[x]+0.1, round(cor_coefs[i,x],2), color='k')

    plt.xticks(ticks = positions+0.3, labels = ticklabels)
    plt.yticks(ticks = positions+0.3, labels = ticklabels)

    plt.title(f"Space-Time Correlation Matrices of WSs, K = {k}")
   
    if save_path != None:
        plt.savefig(save_path + f'{k}k_space_time_correlation_matrix.png')

    plt.show()
    plt.close()


    # old version that doesnt take into account time correlation

    # all_rfo = np.zeros((k,len(cluster_labels.mean(('time')).values.flatten())))
    # all_rfo = cluster_labels.values.flatten()
    # # Plotting the rfo of each cluster
    # # for cluster in range(0,k):
    # #     # Calculating rfo
    # #     rfo = np.sum(cluster_labels==cluster, axis=0) / np.sum(cluster_labels >= 0, axis=0) * 100
    # #     all_rfo[cluster] = rfo.values.flatten()

    # all_rfo = np.ma.masked_invalid(all_rfo)


    # # Creating Correlation pcolormesh
    # plt.figure(figsize=(8, 6), dpi=150)
    # cor_coefs = np.zeros((k,k))
    # for i in range (k):
    #     for x in range (k):
    #         cor_coefs[i,x] = np.ma.corrcoef(all_rfo[i],all_rfo[x])[0,1]

    # cmap = plt.cm.get_cmap('Spectral').reversed()
    # im = plt.pcolormesh(cor_coefs, vmin = -1, vmax =1, cmap = cmap)
    # plt.colorbar(im)

    # ticklabels = []
    # for i in range(k):
    #     ticklabels.append(f'WS{i+1}')

    # positions = np.arange(k)+0.2
    # for i in range (k):
    #     for x in range (k):
    #         plt.text(positions[i],positions[x]+0.1, round(cor_coefs[i,x],2), color='palevioletred')

    # plt.xticks(ticks = positions+0.3, labels = ticklabels)
    # plt.yticks(ticks = positions+0.3, labels = ticklabels)

    # plt.title(f"Spatial Correlation Matrices of WSs, K = {k}")

    # plt.show()

# Create correlation matricies between the cluster centers of k and (k+1) CRs
def kp1_histogram_cor(cl1, cl2, save_path):

    # Creating Correlation pcolormesh
    plt.figure(figsize=(8, 6), dpi=150)
    k1, k2 = len(cl1), len(cl2)
    cor_coefs = np.zeros((k1,k2))

    for i in range (k1):
        for x in range (k2):
            cor_coefs[i,x] = np.corrcoef(cl1[i].flatten(),cl2[x].flatten())[0,1]

    cmap = plt.cm.get_cmap('Spectral').reversed()

    im = plt.pcolormesh(cor_coefs, vmin = -1, vmax = 1, cmap = cmap)
    plt.colorbar(im)

    ticklabels = []
    for i in range(k1):
        ticklabels.append(f'CR{i+1}')
    ticklabels2 = []
    for i in range(k2):
        ticklabels2.append(f'CR{i+1}')

    positions = np.arange(k1)+0.2
    positions2 = np.arange(k2)+0.2
    for i in range (k1):
        for x in range (k2):
            plt.text(positions2[x], positions[i]+0.1, round(cor_coefs[i,x],2), color='k')

    plt.yticks(ticks = positions+0.3, labels = ticklabels)
    plt.xticks(ticks = positions2+0.3, labels = ticklabels2)

    plt.title(f"K+1 Histogram Correlation Matrices")

    # mins = np.min(cor_coefs, axis=0)
    # if mins.max() < 0.5:
    #     print(f'k = {k2} is too small. A new pattern has appeared using k = {k1} ')
    # else:
    #     print(f'k = {k2} is too large. A new pattern did not appear going from k = {k1} to k = {k2}')
    
    if save_path != None:
        plt.savefig(save_path + f'{k1}-{k2}_space_time_correlation_matrix.png')

    plt.show()
    plt.close()

    # plt.clf()

    # if np.max(cor_coefs[np.triu_indices(k, k=1)]) > 0.8:
    #     print(f'k = {k} failed the histogram correlation test. The maximum alowable correlation is 0.8, but the maximum correlation is {round(np.max(cor_coefs),2)}')

# %%



# %%

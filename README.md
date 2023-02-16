# Dask on Azure ML Compute using MPI

This sample shows how to run a Dask data preparation task on an Azure ML Compute Cluster.

## Pre-requisistes

To use this sample, you will need to create an Azure ML Workspace. Please read the documentation for instructions: [Create a workspace](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace#create-a-workspace).

We will use the Azure CLI with Azure ML extensions to prepare the platform and run the sample. Please read documentation for installation instructions: [Install and set up the CLI (v2)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-configure-cli?tabs=public).

To make the example CLI commands more generic, we will use two shell variables:

```sh
GROUP=mspc
WORKSPACE=mspc
```

Replace `mspc` with the names of the Resource Group and Azure ML Workspace that you created.

## Create the environment

The file `environment.yml` contains a Conda environment definition, with all the required dependencies to run the sample script.

The minimal required dependencies to run a Dask job using MPI are the following:

- `dask`
- `dask_mpi`
- `mpi4py`

The provided environment includes other dependencies that are only useful for this sample script.

To create the environment in Azure ML, use the following command:

```sh
az ml environment create \
-g $GROUP \
-w $WORKSPACE \
--name dask-mpi \
--conda-file environment.yml \
--image mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04
```

This will create an Azure ML environment called `dask-mpi`.

The base Docker image specified in the environment creation contains the necessary [OpenMPI](https://www.open-mpi.org/) libraries. You can see a full list of available base images in the GitHub repo [AzureML-Containers](https://github.com/Azure/AzureML-Containers).

## Create the compute cluster

We need an Azure ML Compute Cluster to run our script. The command below will create one with the following settings:

- VM size Standard_D8_v3, which is 8vCPU and 32 GiB RAM. See [Supported VM series and sizes](https://learn.microsoft.com/en-us/azure/machine-learning/concept-compute-target#supported-vm-series-and-sizes) for a list of possible options.
- Maximum of 6 instances.
- Use your current SSH key so you can connect to the nodes.

```sh
az ml compute create \
-g $GROUP \
-w $WORKSPACE \
--type AmlCompute \
--name dask-cluster \
--size Standard_D8_v3 \
--max-instances 6 \
--admin-username azureuser \
--ssh-key-value "$(cat ~/.ssh/id_rsa.pub)"
```

## Run the sample script

The included `job.yml` contains an Azure ML job definition to execute the script `prep_nyctaxi.py`.

The important part of that file regarding Dask is the following section:

```yaml
distribution:
  type: mpi
  process_count_per_instance: 8
resources:
  instance_count: 4
```

This is were we request to run the script using an MPI cluster of 4 instances (`instance_count`) and 8 processes per instance (`process_count_per_instance`). You should adjust these numbers according to the configuration of your cluster.

Execute the job using the following command:

```sh
az ml job create -g $GROUP -w $WORKSPACE --file job.yml
```

You can then track the execution of the job in the Azure ML Studio.

## Accessing the Dask dashboard

The Dask dashboard is very useful to understand what is going on in the cluster. This sample shows a way of accessing the dashboard using SSH tunnels.

- Once the script is running, you can find the job in the Azure ML Jobs list.
- Click on the job name to open the job page.
- Click on "Outputs + logs" to access the logs of the job.
- Open the `user_logs` directory. You will see one log per MPI process, in the form `std_log_process_xx.txt`.
- Open the log named `std_log_process_01.txt`, this is where you will find the logs written by the script running on the MPI process of rank 1.
- In this log you will see a line like this: `Dask dashboard on 10.0.0.8:8787`; this gives you the internal IP address of the host where the Dask dashboard is running.

Now you need to open an SSH tunnel between your workstation and the host, so that you can access the dashboard. To do that, you will find the public IP address of your cluster, and use it to open the tunnel.

- In the Azure ML Studio, go to the "Compute" page.
- Click on "Compute Clusters".
- Click on your cluster name, for example `dask-cluster`.
- Click on Nodes. You will see a list of nodes in your cluster. Each node has a "Connection string" value with a clipboard icon. Click on the clickboard icon of any line to get the SSH command to connect to the cluster. It will look like `ssh azureuser@20.a.b.c -p 50003`.

To create the SSH tunnel, use the `-L` argument to indicate that you want to forward the connection from local port 8787 to the remote port, using the information from the logs. The final command should look like this:

```sh
ssh azureuser@20.a.b.c -p 50003 -L 8787:10.0.0.8:8787
```

Run that command, and the tunnel should be established. Connect to `http://localhost:8787/status` with your browser to access the dashboard.

## How it works

The following two lines are enough to set up the Dask cluster over MPI:

```python
# Initialize Dask over MPI
dask_mpi.initialize()
c = Client()
```

This will automatically run the Dask Scheduler on the MPI process with rank 0, the client code on rank 1, and the Dask Workers on the remaining ranks. This means that out of all the distributed processes you requested in your Azure ML job, two are used to coordinate the cluster, and the others to perform the compute tasks.

You can read more in the Dask-MPI documentation: [Dask-MPI with Batch Jobs](https://mpi.dask.org/en/latest/batch.html) and [How Dask-MPI Works](https://mpi.dask.org/en/latest/howitworks.html).

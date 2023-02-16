"""
Preprocess GBIF data using Dask running on Azure ML Compute Cluster.
"""

import argparse
import socket

import dask.dataframe as dd
import dask.distributed
import dask_geopandas as dask_gpd
import dask_mpi
import geopandas as gpd
import planetary_computer
from distributed.scheduler import logger
from pystac_client import Client

GBIF_FILTERS = [
    ("stateprovince", "==", "Washington"),
]

GBIF_CLASSES = ["Aves", "Mammalia", "Reptilia", "Amphibia"]


def main(client, output_path):
    # Access Planetary Computer catalog and find the latest GBIF drop

    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    gbif_latest = list(catalog.search(collections=["gbif"]).get_all_items())[0]

    # Initiate the Parquet read using Dask

    asset = gbif_latest.assets["data"]
    gbif_df = dd.read_parquet(
        asset.href,
        filters=GBIF_FILTERS,
        storage_options=asset.extra_fields["table:storage_options"],
        parquet_file_extension=None,
        arrow_to_pandas=dict(timestamp_as_object=True),
        split_row_groups=True,
    )

    # Subset dataframe

    df_subset = gbif_df[gbif_df["class"].isin(GBIF_CLASSES)].dropna(
        subset=["species", "month", "day"]
    )

    # Convert to geo dataframe

    dask_gdf = dask_gpd.from_dask_dataframe(
        df_subset,
        geometry=dask_gpd.points_from_xy(
            df_subset, x="decimallongitude", y="decimallatitude", z=None
        ),
    ).set_crs("epsg:4326")

    # Read ecoregions file

    with open("us_eco_l3.zip", "rb") as file:
        ecoregions = gpd.read_file(file).to_crs("epsg:4326")

    # Spatial join

    gbif_with_region = dask_gdf.sjoin(ecoregions, how="inner", predicate="intersects")

    # Filter regions

    gbif_filtered = gbif_with_region[
        gbif_with_region["US_L3NAME"].isin(["Puget Lowland", "North Cascades"])
    ]

    # Write outputs
    # This will trigger the computation of all previous operations
    # on the Dask cluster. There will be one output CSV file per
    # partition (i.e., thousands)

    gbif_filtered.to_csv(f"{output_path}/output-*.csv")


if __name__ == "__main__":
    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path")
    args = parser.parse_args()
    output_path = args.output_path

    # Initialize Dask over MPI
    dask_mpi.initialize()
    client = dask.distributed.Client()

    # Find dashboard
    host = client.run_on_scheduler(socket.gethostname)
    port = client.scheduler_info()["services"]["dashboard"]
    logger.info(f"Dask dashboard on {host}:{port}")

    main(client, output_path)

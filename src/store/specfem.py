import types

import store.simple
from store.simple import *

def specfem_rewrite_settings(params_dict):
    if "mpi-slots" not in params_dict:
        params_dict["mpi-slots"] = "999"

    NB_CORE_ON_MACHINES = 8

    machines = int(int(params_dict["processes"]) / int(params_dict["mpi-slots"]))
    if machines * int(params_dict["mpi-slots"]) != int(params_dict["processes"]):
        machines += 1
    params_dict["machines"] = str(machines)

    if "network" in params_dict:
        network = params_dict["network"]
        del params_dict["network"]
        if network != "default":
            params_dict["platform"] += f"_{network}"
        else:
            if params_dict["platform"] == "openshift" and network == "default":
                params_dict["platform"] = "openshift_sdn"

    if params_dict["platform"] == "podman":
        params_dict["platform"] = "baremetal_podman"

    if params_dict['expe'] != "NVa100":
        del params_dict["processes"]

    if "gpu" in params_dict:
        if params_dict['gpu'].isdigit():
            params_dict["gpu"] = f":{int(params_dict['gpu']):02d}"
        else:
            params_dict['gpu'] = ":"+params_dict['gpu']

    del params_dict['driver']


    if "relyOnSharedFS" not in params_dict:
        params_dict["relyOnSharedFS"] = "False"

    params_dict["run"] = str(params_dict.get("run", 0))+"."
    params_dict["@run"] = params_dict["run"]
    del params_dict["run"]

    params_dict["relyOnSharedFS"] = params_dict["relyOnSharedFS"].lower()

    return params_dict

store.custom_rewrite_settings = specfem_rewrite_settings


def specfem_parse_results(dirname, import_settings):
    results = types.SimpleNamespace()

    try:
        with open(f"{dirname}/timing") as f:
            results.time = float(f.read().strip())
    except FileNotFoundError as e:
        print(f"ERROR: Could not find 'timing' file in {dirname} ...")
        raise e
    return [({}, results)]
store.simple.custom_parse_results = specfem_parse_results

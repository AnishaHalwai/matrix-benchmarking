import os, types, itertools, datetime
import subprocess

import common

class Matrix():
    def __init__(self, mode, yaml_desc):
        self.yaml_desc = yaml_desc
        self.mode = mode

    def run(self, exe):
        exe.expe_cnt = types.SimpleNamespace()
        exe.expe_cnt.total = 0
        exe.expe_cnt.current_idx = 0
        exe.expe_cnt.executed = 0
        exe.expe_cnt.recorded = 0
        exe.expe_cnt.errors = 0

        expe_ran = []
        for expe in self.yaml_desc['run']:
            if not expe or expe.startswith("_"):
                exe.log(f"Skip disabled expe '{expe}'")
                continue

            stop = self.do_run_expe(exe, expe)
            if stop: break
            expe_ran.append(expe)

        exe.log(f"Ran {len(expe_ran)} matri{'ces' if len(expe_ran) > 1 else 'x'}:", ", ".join(expe_ran))
        exe.log(f"Out of {exe.expe_cnt.total} experiments configured:")
        if exe.dry:
            exe.log(f"- {exe.expe_cnt.executed} would have been executed,")
        else:
            exe.log(f"- {exe.expe_cnt.executed} have been executed,")
        exe.log(f"- {exe.expe_cnt.recorded} were already recorded,")
        exe.log(f"- {exe.expe_cnt.errors} failed.")

    def do_run_expe(self, exe, expe):
        exe.log("setup()")

        try:
            yaml_expe = self.yaml_desc['expe'][expe]
        except KeyError as e:
            exe.log(f"ERROR: Cannot run '{expe}': expe matrix not defined.")
            raise e

        context = types.SimpleNamespace()
        context.params = types.SimpleNamespace()

        all_settings_items = [[(name, value) for value in (values if isinstance(values, list) else str(values).split(", "))]
                    for name, values in (yaml_expe.get("settings") or {}).items()]

        exe.expe_cnt.total += sum(1 for _ in itertools.product(*all_settings_items))

        context.expe = expe
        context.expe_dir = f"{common.RESULTS_PATH}/{self.mode}/{context.expe}"
        context.path_tpl = self.yaml_desc['path_tpl']
        context.remote_mode = self.yaml_desc.get('remote_mode', False)
        context.script_tpl = self.yaml_desc['script_tpl']
        context.stop_on_error = self.yaml_desc.get('stop_on_error', False)

        # do fail in drymode if we cannot create the directories
        os.makedirs(context.expe_dir, exist_ok=True)

        stop = self.do_run_matrix(exe, all_settings_items, context, yaml_expe)
        if stop: return stop

        exe.log("#")
        exe.log(f"# Finished with '{context.expe}'")
        exe.log("#")

        return False

    def do_run_matrix(self, exe, all_settings_items, context, yaml_expe):
        for settings_items in itertools.product(*all_settings_items):
            settings = dict(settings_items)
            settings['expe'] = context.expe
            exe.expe_cnt.current_idx += 1

            if "extra" in settings:
                extra = settings["extra"]
                del settings["extra"]

                for kv in extra.split(", "):
                    k, v = kv.split("=")
                    settings[k] = v

            key = common.Matrix.settings_to_key(settings)

            if key in common.Matrix.processed_map:
                exe.log(f"experiment {exe.expe_cnt.current_idx}/{exe.expe_cnt.total} already recorded, skipping")
                exe.log(">", common.Matrix.processed_map[key].location.replace(common.RESULTS_PATH+f"/{self.mode}/", ''))
                exe.expe_cnt.recorded += 1
                continue

            bench_common_path = context.path_tpl.format(**settings)
            bench_uid = datetime.datetime.today().strftime("%Y%m%d_%H%M%S_%f")
            bench_fullpath = f"{context.expe_dir}/{bench_common_path}{bench_uid}"

            if not exe.dry:
                os.makedirs(bench_fullpath)

            exe.log("---")
            exe.log(f"running {exe.expe_cnt.current_idx}/{exe.expe_cnt.total}")
            for k, v in settings.items():
                exe.log(f"    {k}: {v}")

            ret = self.execute_benchmark(bench_fullpath, settings, context, exe)
            if ret != None and not ret:
                exe.expe_cnt.errors += 1
                if context.stop_on_error:
                    print("Stopping on error.")
                    return True

            exe.expe_cnt.executed += 1
        return False

    def execute_benchmark(self, bench_fullpath, settings, context, exe):
        if not exe.dry:
            with open(f"{bench_fullpath}/settings", "w") as f:
                for k, v in settings.items():
                    print(f"{k}={v}", file=f)
                print(f"", file=f)

        settings_str = ""
        for k, v in settings.items():
            settings_str += f" '{k}={v}'"

        script = context.script_tpl.format(**settings)
        script_fullpath = os.path.realpath(os.getcwd()+'/../') + f"/{script}"

        cmd = f"{script_fullpath} {settings_str} 1> >(tee stdout) 2> >(tee stderr >&2)"
        if exe.dry:
            exe.log(f"""\n
Results: {bench_fullpath.replace(common.RESULTS_PATH+'/', '')}
Command: {script} {settings_str}
---
""")

            return None
        elif context.remote_mode:
            print(f"""
cd "{bench_fullpath}"
if [[ "$(cat ./exit_code)" != 0 ]]; then
  {cmd}
  echo "$?" > ./exit_code
else
  echo "Already recorded."
fi
""")
            return None

        # no need to check here if ./exit_code exists and == 0,
        # we wouldn't reach this step if it did
        # (whereas the remote_mode generated script can be executed multiple times)

        exe.log(f"cd {bench_fullpath}")
        exe.log(cmd)

        proc = subprocess.run(cmd, cwd=bench_fullpath, shell=True, executable='/bin/bash')
        exe.log(f"exit code: {proc.returncode}")
        # ^^^ blocks until the process terminates
        with open(f"{bench_fullpath}/exit_code", "w") as f:
            print(f"{proc.returncode}", file=f)

        return proc.returncode == 0

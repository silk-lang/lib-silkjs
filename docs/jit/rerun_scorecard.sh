set -u
# Full scorecard rerun: bash docs/jit/rerun_scorecard.sh <out-dir> (about 2 h, nothing else may build or measure meanwhile).
# Then: python3 docs/jit/latest_section.py <results-folder> "<title>" after copying the outputs to docs/jit/jit-scorecard-results/<folder>/.
R=$(realpath -m "$1"); mkdir -p $R
export PATH="$HOME/.silk/bin:$PATH" SILK_CLANG=$HOME/llvm-22.1.8/bin/clang NODE_REFERENCE=$HOME/node24/node-v24.22.3-linux-x64/bin/node
cd "$(dirname "$0")/../../modules/engine"
echo "build $(date -u +%H:%M:%S)"; timeout 2400 silk build --release > $R/engine-build.log 2>&1; echo "engine exit $?"
(cd ../jit/shell && timeout 2400 silk build --release > $R/shell-build.log 2>&1; echo "shell exit $?")
timeout 900 silk task bench-report --out /tmp/scorecard-probe > /dev/null 2>&1
until ! ps -eo args | grep -q '^[^ ]*silkc'; do sleep 10; done
echo "kernels $(date -u +%H:%M:%S)"; timeout 3000 python3 scripts/jit_kernels.py --rounds 7 --json $R/kernels.json > $R/kernels.log 2>&1; echo "kernels exit $?"
echo "coverage $(date -u +%H:%M:%S)"; timeout 7200 python3 scripts/jit_coverage.py --instructions --plain-instructions --kernels --json $R/coverage.json > $R/coverage.log 2>&1; echo "coverage exit $?"
echo "coverage-calls $(date -u +%H:%M:%S)"; timeout 7200 python3 scripts/jit_coverage.py --instructions --kernels --calls --json $R/coverage-calls.json > $R/coverage-calls.log 2>&1; echo "coverage-calls exit $?"
until ! ps -eo args | grep -q '^[^ ]*silkc'; do sleep 10; done
echo "octane $(date -u +%H:%M:%S)"; timeout 9000 silk task bench-octane --engines silkjs,silkjs-jit,silkjs-jit-calls,v8-jitless,v8-jit,jsc-nojit,jsc-jit --out $R/harness > $R/bench-octane.log 2>&1; echo "octane exit $?"
timeout 600 silk task bench-report --native --out $R/harness > $R/report--native.log 2>&1; echo "report exit $?"
python3 ../../docs/jit/summary_jit.py $R/harness/octane.json > $R/summary.log 2>&1
echo "octane part done $(date -u +%H:%M:%S)"
E=silkjs,silkjs-jit,silkjs-jit-calls,v8-jit,jsc-jit
echo "startup $(date -u +%H:%M:%S)"; timeout 1200 silk task bench-startup --engines $E --out $R/harness > $R/bench-startup.log 2>&1; echo "startup exit $?"
echo "warmup $(date -u +%H:%M:%S)"; timeout 3600 silk task bench-warmup richards deltablue crypto raytrace navier-stokes box2d --engines $E --out $R/harness > $R/bench-warmup.log 2>&1; echo "warmup exit $?"
echo "ALLDONE $(date -u +%H:%M:%S)"

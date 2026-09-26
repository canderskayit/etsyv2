from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def env_path(name: str, required: bool = True) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        if required:
            raise RuntimeError(f"Missing environment path: {name}")
        return None
    return Path(value)


def jsx_string(value: str | Path) -> str:
    return json.dumps(str(value).replace("\\", "/"), ensure_ascii=False)


def selected_psds(folder: Path) -> list[Path]:
    files = sorted(folder.glob("*.psd"), key=lambda item: item.name.lower())
    raw = os.environ.get("CODEX_MOCKUP_PSD_STEMS", "").strip()
    if not raw:
        return files
    wanted = {item.strip().lower() for item in re.split(r"[|,;]", raw) if item.strip()}
    selected = [path for path in files if path.stem.strip().lower() in wanted]
    if len(selected) != len(wanted):
        found = {path.stem.strip().lower() for path in selected}
        missing = sorted(wanted - found)
        raise RuntimeError("Selected PSD files are missing: " + ", ".join(missing))
    return selected


def replace_js_function(source: str, function_name: str, replacement: str) -> str:
    match = re.search(rf"\bfunction\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{", source)
    if not match:
        raise RuntimeError(f"JSX function not found: {function_name}")
    brace_start = source.find("{", match.start())
    depth = 0
    quote = ""
    escaped = False
    for index in range(brace_start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[: match.start()] + replacement + source[index + 1 :]
    raise RuntimeError(f"JSX function is not balanced: {function_name}")


def video_helpers() -> str:
    return Path(__file__).with_name("video_mockup_helpers.jsx").read_text(encoding="utf-8")


def status_helpers(status_path: Path) -> str:
    return r'''function writeBatchStatus(phase, count, videoError, ok) {
        var message = String(videoError || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r/g, "\\r").replace(/\n/g, "\\n").replace(/\t/g, "\\t");
        var file = new File(STATUS_PATH);
        file.encoding = "UTF8";
        file.open("w");
        file.write('{"ok":' + (ok === false ? 'false' : 'true') + ',"phase":"' + phase + '","mockups":' + count + ',"video_error":"' + message + '","error":"' + message + '"}');
        file.close();
    }'''.replace("STATUS_PATH", jsx_string(status_path))


def build_run_batch(psds: list[Path], source: Path, output: Path, video_psd: Path | None) -> str:
    psd_lines = ",\n            ".join(jsx_string(path) for path in psds)
    video_call = ""
    if video_psd:
        video_call = f'''writeBatchStatus("video", success, "", true);
        try {{
            app.purge(PurgeTarget.ALLCACHES);
            processOneVideoSimple({jsx_string(video_psd)}, {jsx_string(source)}, {jsx_string(output / "vertical.mp4")});
        }} catch (videoError) {{
            videoErrorMessage = String(videoError.message || videoError) + " (line " + videoError.line + ")";
            log.push("Video export failed: " + videoErrorMessage);
        }}'''
    return f'''function runBatch() {{
        var outputFolder = new Folder({jsx_string(output)});
        if (!outputFolder.exists) outputFolder.create();
        var posterFiles = [{jsx_string(source)}];
        var psdFiles = [{psd_lines}];
        if (psdFiles.length === 0) throw new Error("No selected PSD files");
        var jobs = buildJobQueue(posterFiles, psdFiles, outputFolder);
        var progress = createProgressUI(jobs.length);
        var log = [], success = 0, videoErrorMessage = "";
        writeBatchStatus("mockups", 0, "", true);
        try {{
            for (var index = 0; index < jobs.length; index++) {{
                var job = jobs[index];
                progress.update(index + 1, jobs.length, job.posterName, job.psdName);
                try {{
                    processOne(job.psdPath, job.posterPath, job.outPath);
                    success++;
                }} catch (error) {{
                    log.push("[" + job.psdName + "] " + error.message);
                }}
                writeBatchStatus("mockups", success, "", true);
            }}
        }} finally {{ progress.close(); }}
        {video_call}
        var summary = new File({jsx_string(output / "mockup-batch-summary.txt")});
        summary.encoding = "UTF8";
        summary.open("w");
        summary.write("Completed: " + success + "/" + jobs.length + "\\n" + log.join("\\n"));
        summary.close();
        writeBatchStatus("done", success, videoErrorMessage, true);
    }}'''


def main() -> int:
    source_path = env_path("CODEX_MOCKUP_SOURCE_PATH")
    ready_root = env_path("CODEX_MOCKUP_READY_DIR")
    psd_folder = env_path("CODEX_MOCKUP_PSD_FOLDER")
    base_jsx = env_path("CODEX_MOCKUP_BASE_JSX")
    photoshop = env_path("CODEX_PHOTOSHOP_EXE")
    generated_jsx = env_path("CODEX_MOCKUP_GENERATED_JSX")
    video_psd = env_path("CODEX_MOCKUP_VIDEO_PSD", required=False)
    if os.environ.get("CODEX_MOCKUP_SKIP_VIDEO") == "1":
        video_psd = None
    status_path = env_path("CODEX_MOCKUP_STATUS_FILE")
    folder_name = os.environ.get("CODEX_MOCKUP_FOLDER_NAMES", "").strip()

    for required in (source_path, ready_root, psd_folder, base_jsx, photoshop):
        if required is None or not required.exists():
            raise FileNotFoundError(str(required))
    if video_psd and not video_psd.exists():
        video_psd = None

    psds = selected_psds(psd_folder)
    if not psds:
        raise RuntimeError(f"No PSD files found in {psd_folder}")

    output_folder = ready_root / (folder_name or source_path.stem)
    output_folder.mkdir(parents=True, exist_ok=True)
    source_copy = output_folder / source_path.name
    shutil.copyfile(source_path, source_copy)
    os.utime(source_copy, None)

    source = base_jsx.read_text(encoding="utf-8-sig")
    source = source.replace('var SMART_LAYER_NAME = "Kare 1";', "var SMART_LAYER_NAME = " + json.dumps(os.environ.get("ETSY_V2_SMART_LAYER", "Kare 1"), ensure_ascii=False) + ";")
    source = replace_js_function(source, "runBatch", build_run_batch(psds, source_copy, output_folder, video_psd))
    source = source.rsplit("})();", 1)[0] + video_helpers() + "\n})();\n"
    source = source.replace("#target photoshop", "")
    source = source.replace("        if (!automatedRun) {", "        if (automatedRun) { throw e; }\n        if (!automatedRun) {", 1)
    source = "#target photoshop\nvar CODEX_AUTOMATED_RUN = true;\n" + status_helpers(status_path) + "\ntry {\n" + source + '\n} catch(error) { writeBatchStatus("error", 0, String(error), false); }\n'
    generated_jsx.parent.mkdir(parents=True, exist_ok=True)
    generated_jsx.write_text(source, encoding="utf-8-sig")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from server import launch_photoshop_jsx
    launch_photoshop_jsx(photoshop, generated_jsx)
    print(f"Photoshop workflow started: {generated_jsx}")
    print(f"Output folder: {output_folder}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise

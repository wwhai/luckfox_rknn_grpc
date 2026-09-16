from pathlib import Path
import shutil
import tempfile

from grpc_tools import protoc


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "proto"
OUTPUT_DIR = ROOT / "client" / "generated"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="luckfox-grpc-") as temp_name:
        temp_dir = Path(temp_name)
        proto_file = temp_dir / "rknn_accelerator.proto"
        shutil.copy2(PROTO_DIR / "rknn_accelerator.proto", proto_file)
        result = protoc.main(
            [
                "grpc_tools.protoc",
                f"-I{temp_dir}",
                f"--python_out={temp_dir}",
                f"--grpc_python_out={temp_dir}",
                str(proto_file),
            ]
        )
        if result != 0:
            raise SystemExit(result)
        for generated_file in ("rknn_accelerator_pb2.py", "rknn_accelerator_pb2_grpc.py"):
            shutil.copy2(temp_dir / generated_file, OUTPUT_DIR / generated_file)
    print(f"Generated Python stubs in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
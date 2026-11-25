{
  perSystem =
    { pkgs, ... }:
    let
      python = pkgs.python3.withPackages (p: [
        p.numpy
        p.pillow
      ]);
    in
    {
      packages.sprite-sheet = pkgs.writeShellApplication {
        name = "sprite-sheet";
        runtimeInputs = [
          pkgs.blender
          pkgs.ffmpeg
        ];
        text = ''
          usage() {
            echo "usage: sprite-sheet render CHARACTER.blend OUT.png ACTION... [--cell N] [--step N] [--turn DEG]" >&2
            echo "         [--frame-height H] [--ground-margin M] [--forward-shift S]" >&2
            echo "       sprite-sheet demo SHEET.png OUT.mp4 --idle ACTION --run ACTION" >&2
            exit 2
          }
          [ $# -ge 1 ] || usage
          cmd=$1
          shift
          case $cmd in
            render)
              [ $# -ge 1 ] || usage
              blend=$1
              shift
              exec blender -b --factory-startup --disable-autoexec --python-exit-code 1 "$blend" \
                --python ${./scripts}/render.py -- "$@"
              ;;
            demo) exec ${python}/bin/python3 -I ${./scripts}/demo.py "$@" ;;
            *) usage ;;
          esac
        '';
      };
    };
}

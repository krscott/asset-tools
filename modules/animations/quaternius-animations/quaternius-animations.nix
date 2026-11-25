{
  perSystem =
    { pkgs, ... }:
    {
      packages.quaternius-animations = pkgs.writeShellApplication {
        name = "quaternius-animations";
        runtimeInputs = [ pkgs.blender ];
        text = ''exec ${pkgs.python3}/bin/python3 -I ${./scripts}/main.py "$@"'';
      };
    };
}

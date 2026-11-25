{
  perSystem =
    { pkgs, self', ... }:
    {
      devShells.default = pkgs.mkShell {
        packages = builtins.attrValues self'.packages ++ [ pkgs.blender ];
      };
    };
}

{
  description = "anki with locked, Nix-resolved add-ons";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        anki-purifier = import ./nix/scope.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (
        system:
        let
          p = (pkgsFor system).anki-purifier;
        in
        {
          default = p.cli;
          anki = p.original;
          xvfb = (pkgsFor system).xvfb-run;
          gui-test-env =
            let
              pkgs = pkgsFor system;
            in
            pkgs.runCommand "purifier-gui-test-environment" { } ''
              mkdir -p "$out/bin"
              ln -s ${pkgs.lib.getBin pkgs.dbus}/bin/dbus-run-session "$out/bin/dbus-run-session"
              ln -s ${pkgs.lib.getBin pkgs.dbus}/bin/dbus-daemon "$out/bin/dbus-daemon"
              ln -s ${
                pkgs.makeFontsConf {
                  fontDirectories = [
                    pkgs.dejavu_fonts
                    pkgs.noto-fonts
                  ];
                }
              } "$out/fonts.conf"
            '';
        }
      );
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/anki-purifier";
        };
      });
      lib.anki-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = (pkgsFor system).anki-purifier;
          build = p.buildAnkiProject {
            src = ./examples/minimal;
            doCheck = true;
            checkCommand = ''test -s "$out/notes.txt"'';
          };
        in
        {
          resource-projections = import ./tests/resource-projections.nix {
            pkgs = pkgsFor system;
            build = p.buildAnkiProject;
          };
          cli = p.cli;
          inherit (build.packages) environment project;
          release = build.release;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}

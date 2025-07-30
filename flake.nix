{
  description = "A development shell for the pycalista-ista Python project";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      # Define the systems this flake supports.
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];

      # Helper function to generate an output for each supported system.
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Helper function to get the nixpkgs set for a specific system.
      pkgsFor = system: import nixpkgs { inherit system; };

    in
    {
      devShell = forAllSystems (system:
        let
          pkgs = pkgsFor system;

          # Create a Python environment with all project dependencies.
          # Using Python 3.12 as specified in pyproject.toml
          pythonWithProjectDeps = pkgs.python3.withPackages (ps: with ps; [
            # Runtime dependencies from [project].dependencies
            requests
            pandas
            xlrd
            unidecode
            aiohttp
            yarl

            # Build system dependencies
            setuptools
            wheel

            # Dev dependencies from [project.optional-dependencies].dev
            aioresponses
            pytest
            pytest-cov
            pytest-asyncio
            requests-mock
            black
            isort
            xlwt
          ]);
        in
        pkgs.mkShell {
          name = "pycalista-ista-dev";

          # The list of packages available in the shell.
          # This includes our full Python environment plus other native tools.
          packages = with pkgs; [
            pythonWithProjectDeps
            pre-commit
          ];

          # Hook to run when entering the shell.
          shellHook = ''
            echo "✅ Nix dev environment for 'pycalista-ista' is ready."

            # Add the project root to PYTHONPATH so that Python can find your local modules,
            # which is great for running tests without a full installation.
            export PYTHONPATH=$PWD:$PYTHONPATH

            echo "   Tip: Run 'pytest' to execute the test suite."
          '';
        });
    };
}
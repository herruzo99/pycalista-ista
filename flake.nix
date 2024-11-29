{
  description = "python dev environment";

  # to activate, type `nix develop` while in the repo dir or a subdir.
  # or use direnv to automatically do so (see .envrc)
  # for best results, don't have a global python installed.  mixing python
  # versions can make for venv problems.

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pname = "python dev environment";
        pkgs = nixpkgs.legacyPackages."${system}";
        venvDir = "v-env";
      in
        rec {
          inherit pname;

          # `nix develop`
          devShell = pkgs.mkShell {
            buildInputs = [
              pkgs.python312
              pkgs.libGL
              pkgs.stdenv.cc.cc.lib
            ];
            nativeBuildInputs = with pkgs; [
              python312Packages.python
              python312Packages.python-lsp-server
              python312Packages.autopep8
            ];
            LD_LIBRARY_PATH="${pkgs.libGL}/lib/:${pkgs.stdenv.cc.cc.lib}/lib/:${pkgs.glib.out}/lib/";


            shellHook = ''
                # create a virtualenv if there isn't one.

                # DOESN'T install deps for the python app.  Do that once `nix develop` runs with
                # $ cd src
                # $ pip install -r ./requirements.txt

                if [ -d "${venvDir}" ]; then
                  echo "Skipping venv creation, '${venvDir}' already exists"
                else
                  echo "Creating new venv environment in path: '${venvDir}'"
                  # Note that the module venv was only introduced in python 3, so for 2.7
                  # this needs to be replaced with a call to virtualenv
                  python -m venv "${venvDir}"
                  # unescape to attempt use
                  # \$\{pythonPackages.python.interpreter\} -m venv "${venvDir}"
                fi

                # activate our virtual env.
                source "${venvDir}/bin/activate"
              '';
          };
        }
    );
}

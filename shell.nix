{ pkgs ? import <nixpkgs> {}, ... }:
(pkgs.buildFHSUserEnv {
  name = "pipzone";
  targetPkgs = pkgs: (with pkgs; [
    gcc
    python313
    python313Packages.pip
    uv
    ffmpeg
    turbo
  ]);

  runScript = "bash  --rcfile <(echo '. ~/.bashrc; . venv/bin/activate')";
}).env
# Phase: 01-multibyte-support

## Overview

The latest MeshCore firmware (v1.14) has introduced multibyte support for multi-byte path hashes. The latest version of the MeshCore Python bindings (meshcore_py) has been updated to use this. This allows longer repeater IDs per hop, but reduces the maximum allowed hops. Nodes running older firmware only support 1-byte path hashes and will not receive messages if other nodes use multibyte path hashes.

## Goals

* Update Receiver/Sender component to use latest version of MeshCore Python bindings that support multibyte path hash handling.

## Requirements

* Must remain backwards compatible with previous version. Confirm whether this is handled by the Python library.

## References

* https://github.com/meshcore-dev/meshcore_py/releases/tag/v2.3.0

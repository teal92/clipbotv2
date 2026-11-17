# Upstream source requests — drafts, not sent

These requests contain only public component versions and public binary hashes. No customer records, private code, credentials or logs are included. Sending email or opening a public issue requires the owner's explicit authorization.

## Gyan FFmpeg build maintainer

Destination: builds@gyan.dev, as documented at https://www.gyan.dev/ffmpeg/builds/

Subject: Matching source and build recipe for FFmpeg 9.0.1 full Windows build

Hello,

We are preparing a Windows application release using your official ffmpeg-9.0.1-full_build binaries and want to retain the exact matching source and build materials before redistribution.

The build identifies FFmpeg commit bf1b838f2a. The ffmpeg.exe SHA256 is 57c56e369d5b4873b4d93fc1a1d833cb7cd8bc9325c14b05c34ce60b22842d8a; ffprobe.exe is afe05347caaabe479b3c4eae71992b6ec1e11c57266a1d665deb0f9fe9847208. We have preserved the distributed README and verified the official release archive.

Could you point us to the complete matching source package or historical build recipe, including external-library source revisions, patches, build scripts and toolchain package references for this particular build? A current recipe for a different version would not establish the required match.

Thank you,
YOUR COMPANY NAME

## PyAV native-build maintainer

Destination: public issue at https://github.com/PyAV-Org/pyav-ffmpeg/issues

Title: Historical Windows runtime package/source references for vendor 8.1.2-1

We are preparing an application release using the PyAV 18.0.0 Windows wheel and want to preserve matching native source/build materials before distribution.

We verified the official wheel and vendor 8.1.2-1 archive, pinned vendor commit a71bf9279f7a4659154b68ba6783e89be460bcd5, the complete patch tree, and the source archives named by that recipe. The remaining gap is the historical Windows runtime packages copied from the GCC/MSYS2 environment: libgcc_s_seh-1.dll, libiconv-2.dll, libstdc++-6.dll, libwinpthread-1.dll and zlib1.dll.

Could you provide the package versions/source package references and original build environment record for those copied DLLs? The identified Windows job IDs are 84127236786 and 83334584701; authenticated log retrieval now returns HTTP 410. References for the original fetched config.guess/config.sub revisions would also help.

We are looking for records corresponding to this existing binary release, rather than the current branch. No assertion about the project's compliance is intended; we want to complete our own release evidence accurately.

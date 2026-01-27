class Biliobjclint < Formula
  desc "Objective-C code linting tool with Xcode integration and Claude AI auto-fix"
  homepage "https://github.com/pjocer/BiliObjcLint"
  url "https://github.com/pjocer/BiliObjcLint/archive/refs/tags/v1.0.10.tar.gz"
  sha256 "a5bb9fcb504b2b2e8e6a5ccefb3ea4d9fc7851ff2645da855fad80e7cd9c4cfe"
  license "MIT"
  head "https://github.com/pjocer/BiliObjcLint.git", branch: "main"

  depends_on "python@3.13"

  def install
    # Install all files to libexec
    libexec.install Dir["*"]

    # Create virtual environment
    venv = libexec/".venv"
    system "python3.13", "-m", "venv", venv

    # Install Python dependencies
    system venv/"bin/pip", "install", "-r", libexec/"requirements.txt"

    # Create wrapper script
    (bin/"biliobjclint").write <<~EOS
      #!/bin/bash
      exec "#{venv}/bin/python3" "#{libexec}/scripts/biliobjclint.py" "$@"
    EOS

    # Create Xcode integration script wrapper
    (bin/"biliobjclint-xcode").write <<~EOS
      #!/bin/bash
      exec "#{venv}/bin/python3" "#{libexec}/scripts/xcode_integrator.py" "$@"
    EOS
  end

  def caveats
    <<~EOS
      BiliObjCLint has been installed!

      To integrate with Xcode project:
        biliobjclint-xcode /path/to/your/project.xcodeproj

      To run lint manually:
        biliobjclint --help

      Configuration file will be created at:
        /path/to/project/.biliobjclint.yaml

      To update to the latest version:
        brew update && brew upgrade biliobjclint
    EOS
  end

  test do
    # Create a test Objective-C file
    (testpath/"test.m").write <<~EOS
      #import <Foundation/Foundation.h>
      @interface TestClass : NSObject
      @end
      @implementation TestClass
      @end
    EOS

    # Run lint on test file
    output = shell_output("#{bin}/biliobjclint --files #{testpath}/test.m --no-oclint 2>&1", 0)
    assert_match(/BiliObjCLint|violations|Checking/, output)
  end
end

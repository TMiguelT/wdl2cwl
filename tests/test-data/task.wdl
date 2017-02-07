task wc2_tool {
  File file1
  command {
    wc ${file1}
  }
  output {
    Int count = read_int(stdout())
  }
}

workflow count_lines4_wf {
  Array[File] files
  scatter(f in files) {
    call wc2_tool {
      input: file1=f,
        RefFasta=f
    }
  }
  output {
    wc2_tool.count
  }
}
// Dump pseudo-C decompilation for every function of the current program.
// Output dir comes from the script args, so it works for any imported build.
//   analyzeHeadless <projdir> <proj> -process <EXE> -noanalysis -readOnly \
//     -scriptPath $REBOX_GHIDRA_SCRIPTS -postScript GhidraDumpDecompArg.java <outdir>
// (or simply: ghidra-dump <projdir> <proj> <EXE> <outdir>)
//
// Output: {outdir}/{addr}_{name}.c plus _index.tsv (address, name, size, file).
// Origin: re/tools/GhidraDumpDecompArg.java of the Cyberia RE project.
//@category RE-Toolbox
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.FunctionManager;

public class GhidraDumpDecompArg extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("usage: GhidraDumpDecompArg.java <outdir>");
            return;
        }
        String outDir = args[0];
        new File(outDir).mkdirs();

        DecompInterface decomp = new DecompInterface();
        decomp.setOptions(new DecompileOptions());
        if (!decomp.openProgram(currentProgram)) {
            println("openProgram failed");
            return;
        }

        FunctionManager fm = currentProgram.getFunctionManager();
        FunctionIterator iter = fm.getFunctions(true);

        int ok = 0, fail = 0;
        try (PrintWriter idx = new PrintWriter(new FileWriter(outDir + "/_index.tsv"))) {
            idx.println("address\tname\tsize\tfile");
            while (iter.hasNext()) {
                if (monitor.isCancelled()) break;
                Function func = iter.next();
                String addr = func.getEntryPoint().toString();
                String rawName = func.getName();
                String safe = rawName.replaceAll("[/ :]", "_");
                long size = func.getBody() != null ? func.getBody().getNumAddresses() : 0;
                String outName = addr + "_" + safe + ".c";
                DecompileResults res = decomp.decompileFunction(func, 60, monitor);
                if (res != null && res.decompileCompleted()) {
                    try (PrintWriter f = new PrintWriter(new FileWriter(outDir + "/" + outName))) {
                        f.println("/* " + rawName + " @ " + addr + " (size=" + size + " bytes) */");
                        f.print(res.getDecompiledFunction().getC());
                    }
                    idx.println(addr + "\t" + rawName + "\t" + size + "\t" + outName);
                    ok++;
                } else {
                    String err = res != null ? res.getErrorMessage() : "no result";
                    idx.println(addr + "\t" + rawName + "\t" + size + "\tFAIL: " + err);
                    fail++;
                }
            }
        }
        println("done: " + ok + " ok, " + fail + " fail");
    }
}

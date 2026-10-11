// Decompile every function whose fully-qualified name matches a regex.
// Args: <file containing regex> <output file>
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

public class DumpMatching extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Pattern pattern = Pattern.compile(Files.readString(Path.of(args[0])).trim());
        String outPath = args[1];

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        try (PrintWriter out = new PrintWriter(new FileWriter(outPath))) {
            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
            int count = 0;
            while (it.hasNext() && !monitor.isCancelled()) {
                Function f = it.next();
                String name = f.getName(true);
                if (!pattern.matcher(name).find()) {
                    continue;
                }
                DecompileResults res = decomp.decompileFunction(f, 120, monitor);
                out.println("// ==== " + name + " @ " + f.getEntryPoint());
                if (res.decompileCompleted()) {
                    out.println(res.getDecompiledFunction().getC());
                } else {
                    out.println("// decompile failed: " + res.getErrorMessage());
                }
                count++;
            }
            println("Decompiled " + count + " functions to " + outPath);
        }
        decomp.dispose();
    }
}

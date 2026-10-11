// Map unnamed objc_msgSend stubs to the selector string each one loads.
// Args: <output file>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ResolveStubs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outPath = getScriptArgs()[0];
        try (PrintWriter out = new PrintWriter(new FileWriter(outPath))) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                if (!f.getParentNamespace().getName().equals("objc_stub") || !f.getName().startsWith("FUN_")) {
                    continue;
                }
                String sel = resolve(f);
                out.println(f.getName() + "\t" + (sel == null ? "?" : sel));
            }
        }
    }

    private String resolve(Function f) throws Exception {
        InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            for (Reference ref : ins.getReferencesFrom()) {
                Address to = ref.getToAddress();
                if (!to.isMemoryAddress()) {
                    continue;
                }
                String s = stringAt(to);
                if (s != null) {
                    return s;
                }
                try {
                    long ptr = getLong(to);
                    s = stringAt(toAddr(ptr));
                    if (s != null) {
                        return s;
                    }
                } catch (Exception ignored) {
                }
            }
        }
        return null;
    }

    private String stringAt(Address a) {
        Data d = getDataAt(a);
        if (d != null && d.hasStringValue()) {
            return StringDataInstance.getStringDataInstance(d).getStringValue();
        }
        return null;
    }
}

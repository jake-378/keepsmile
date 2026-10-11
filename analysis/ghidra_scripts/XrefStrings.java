// For each defined string matching a regex, list the functions that reference it,
// following one level of indirection (e.g. CFString structs that point at the chars).
// Args: <file containing regex> <output file>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.TreeSet;
import java.util.regex.Pattern;

public class XrefStrings extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Pattern pattern = Pattern.compile(Files.readString(Path.of(args[0])).trim());
        try (PrintWriter out = new PrintWriter(new FileWriter(args[1]))) {
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            while (it.hasNext() && !monitor.isCancelled()) {
                Data d = it.next();
                if (!d.hasStringValue()) {
                    continue;
                }
                String value = String.valueOf(d.getValue());
                if (!pattern.matcher(value).find()) {
                    continue;
                }
                TreeSet<String> users = new TreeSet<>();
                collect(d.getAddress(), users, 2);
                out.println(d.getAddress() + "\t" + value + "\t" + String.join(", ", users));
            }
        }
    }

    private void collect(Address target, TreeSet<String> users, int depth) {
        for (Reference ref : getReferencesTo(target)) {
            Address from = ref.getFromAddress();
            Function f = getFunctionContaining(from);
            if (f != null) {
                users.add(f.getName(true));
            } else if (depth > 0) {
                Data container = getDataContaining(from);
                if (container != null) {
                    collect(container.getAddress(), users, depth - 1);
                }
            }
        }
    }
}

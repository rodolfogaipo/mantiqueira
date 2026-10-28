// Mantiqueira.exe — abre o programa usando o Python que vem junto na pasta.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Iniciar
{
    [STAThread]
    static void Main()
    {
        string raiz = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string py = Path.Combine(raiz, "python", "pythonw.exe");
        string main = Path.Combine(raiz, "app", "main.py");
        if (!File.Exists(py) || !File.Exists(main))
        {
            MessageBox.Show("A instalação está incompleta.\n\nFalta: " + (File.Exists(py) ? main : py) +
                            "\n\nRode o Instalar-Mantiqueira.exe de novo.", "Mantiqueira",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        var psi = new ProcessStartInfo(py, "\"" + main + "\"");
        psi.WorkingDirectory = Path.Combine(raiz, "app");
        psi.UseShellExecute = false;
        psi.EnvironmentVariables["MANTIQUEIRA_RAIZ"] = raiz;
        psi.EnvironmentVariables["COQUI_TOS_AGREED"] = "1";
        psi.EnvironmentVariables["HF_HUB_OFFLINE"] = "1";
        psi.EnvironmentVariables["TRANSFORMERS_OFFLINE"] = "1";
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";
        psi.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
        Process.Start(psi);
    }
}

package br.com.iptvcast.app

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import br.com.iptvcast.app.databinding.ActivitySettingsBinding
import kotlinx.coroutines.launch

class SettingsActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySettingsBinding
    private val app get() = application as IptvApp

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.inputApiBase.setText(app.prefs.apiBaseUrl)
        binding.txtStatus.text = "Padrao do build: ${br.com.iptvcast.app.BuildConfig.DEFAULT_API_BASE}"

        binding.btnSave.setOnClickListener {
            val url = binding.inputApiBase.text?.toString().orEmpty().trim()
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                Toast.makeText(this, "URL precisa comecar com http://", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            app.prefs.apiBaseUrl = url
            Toast.makeText(this, "Salvo: ${app.prefs.apiBaseUrl}", Toast.LENGTH_SHORT).show()
            finish()
        }

        binding.btnTest.setOnClickListener {
            val draft = binding.inputApiBase.text?.toString().orEmpty().trim().trimEnd('/')
            if (draft.isNotBlank()) {
                app.prefs.apiBaseUrl = draft
            }
            binding.txtStatus.text = "Testando ${app.prefs.apiBaseUrl} ..."
            lifecycleScope.launch {
                try {
                    val h = app.repository.health()
                    val devices = runCatching { app.repository.devices().devices.size }.getOrDefault(0)
                    binding.txtStatus.text =
                        "OK companion\nip=${h.ip}\ndevices=${h.devices ?: devices}\npending=${h.pending}"
                } catch (e: Exception) {
                    binding.txtStatus.text = "Falha: ${e.message}"
                }
            }
        }
    }
}

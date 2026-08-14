package br.com.iptv.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color
import br.com.iptv.app.ui.IptvAppScreen

class MainActivity : ComponentActivity() {
    private val vm: IptvViewModel by viewModels()

    private val importM3u = registerForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            runCatching {
                contentResolver.takePersistableUriPermission(
                    uri,
                    android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
            vm.importM3u(uri)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFFA3E635),
                    background = Color(0xFF020617),
                    surface = Color(0xFF0F172A),
                ),
            ) {
                IptvAppScreen(
                    vm = vm,
                    onImportClick = {
                        importM3u.launch(
                            arrayOf(
                                "audio/x-mpegurl",
                                "application/vnd.apple.mpegurl",
                                "application/x-mpegURL",
                                "text/plain",
                                "*/*",
                            ),
                        )
                    },
                )
            }
        }
    }
}

package br.com.iptv.standalone

import android.app.Application
import br.com.iptv.standalone.cast.CastController
import br.com.iptv.standalone.data.IptvRepository
import br.com.iptv.standalone.server.LocalApiServer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class IptvApp : Application() {
    private val appJob = SupervisorJob()
    val appScope = CoroutineScope(appJob + Dispatchers.Main.immediate)

    lateinit var repository: IptvRepository
        private set
    lateinit var castController: CastController
        private set
    @Volatile
    var apiServer: LocalApiServer? = null
        private set

    override fun onCreate() {
        super.onCreate()
        repository = IptvRepository(this)
        castController = CastController(this).also { it.init() }

        appScope.launch(Dispatchers.IO) {
            if (repository.playlists.value.isEmpty()) {
                repository.importM3uFromAsset("seed/lista-seed.m3u", "lista-seed")
                repository.tryImportFromDownloads()
            }
            startLocalApi()
        }
    }

    @Synchronized
    fun startLocalApi() {
        if (apiServer != null) return
        val server = LocalApiServer(
            context = this,
            repo = repository,
            cast = castController,
            scope = appScope,
        )
        try {
            server.start()
            apiServer = server
        } catch (_: Exception) {
            runCatching { server.stop() }
        }
    }

    override fun onTerminate() {
        runCatching { apiServer?.stop() }
        appJob.cancel()
        super.onTerminate()
    }
}

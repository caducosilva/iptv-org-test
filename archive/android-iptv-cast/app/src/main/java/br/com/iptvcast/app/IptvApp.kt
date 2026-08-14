package br.com.iptvcast.app

import android.app.Application
import br.com.iptvcast.app.backend.CompanionRepository
import br.com.iptvcast.app.data.AppPrefs

class IptvApp : Application() {
    lateinit var prefs: AppPrefs
        private set
    lateinit var repository: CompanionRepository
        private set

    override fun onCreate() {
        super.onCreate()
        prefs = AppPrefs(this)
        repository = CompanionRepository(prefs)
    }
}

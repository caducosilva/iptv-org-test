package br.com.iptv.app

import android.app.Application
import br.com.iptv.app.data.IptvRepository

class IptvApp : Application() {
    lateinit var repository: IptvRepository
        private set

    override fun onCreate() {
        super.onCreate()
        repository = IptvRepository(this)
    }
}

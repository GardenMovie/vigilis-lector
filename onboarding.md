setup mongoURI
ping the cluster

Setup databases
    Hosts, specifications collection
    Metrics, hardwareDay/Hour/Min all with TTLs
Setup triggers
    hourlyRollup
    dailyRollup
Populate specifications with data for this host
    on .env, HOSTNAME string, RAMCAPACITY int, DISKCAPACITY int, CPUMODEL string, GPUMODE string 
    insert document into specifications, remove if theres one with the same hostname
Setup systemd service
    

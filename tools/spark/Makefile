obj-m += scmi_probe.o scmi_scan.o spbm_read.o spbm_hwmon.o

KDIR ?= /lib/modules/$(shell uname -r)/build
MOK_KEY ?= /var/lib/shim-signed/mok/MOK.priv
MOK_CERT ?= /var/lib/shim-signed/mok/MOK.der
SIGN_FILE ?= $(KDIR)/scripts/sign-file

all: modules sign

modules:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

sign: modules
	@for ko in $(PWD)/*.ko; do \
		if [ -f "$(MOK_KEY)" ] && [ -f "$(MOK_CERT)" ]; then \
			sudo $(SIGN_FILE) sha256 $(MOK_KEY) $(MOK_CERT) $$ko && \
			echo "Signed $$ko"; \
		fi; \
	done

probe: all
	-sudo insmod ./scmi_probe.ko 2>&1 || true
	sudo dmesg | grep "scmi_probe" | tail -100

scan: all
	-sudo insmod ./scmi_scan.ko 2>&1 || true
	sudo dmesg | grep "scmi_scan" | tail -30

spbm: all
	-sudo insmod ./spbm_read.ko 2>&1 || true
	sudo dmesg | grep "spbm_read" | tail -60

hwmon: all
	-sudo rmmod spbm_hwmon 2>/dev/null || true
	sudo insmod ./spbm_hwmon.ko
	@sleep 0.5
	sudo dmesg | grep "spbm" | tail -10
	@echo "---"
	@sensors spbm-* 2>/dev/null || \
		(echo "sensors not found, reading sysfs directly:" && \
		 for f in /sys/class/hwmon/hwmon*/name; do \
			if [ "$$(cat $$f 2>/dev/null)" = "spbm" ]; then \
				d=$$(dirname $$f); \
				for p in $$d/power*_label; do \
					[ -f "$$p" ] && echo "$$(cat $$p): $$(cat $${p%_label}_input) uW"; \
				done; \
				for e in $$d/energy*_label; do \
					[ -f "$$e" ] && echo "$$(cat $$e): $$(cat $${e%_label}_input) uJ"; \
				done; \
			fi; \
		done)

hwmon-unload:
	-sudo rmmod spbm_hwmon 2>/dev/null

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

.PHONY: all modules sign probe scan clean

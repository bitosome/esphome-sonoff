YAML_FILES := $(sort $(wildcard *.yaml) $(wildcard minis/*.yaml))
ESPHOME_CONFIGS := switchman_m5_1_gang.yaml switchman_m5_2_gang.yaml thp-experiment.yaml

.PHONY: lint lint-yaml lint-esphome

lint: lint-yaml lint-esphome

lint-yaml:
	@command -v yamllint >/dev/null 2>&1 || { echo "yamllint is not installed. Install it first, for example: pipx install yamllint"; exit 1; }
	yamllint $(YAML_FILES)

lint-esphome:
	@command -v esphome >/dev/null 2>&1 || { echo "esphome is not installed. Install it first, for example: pipx install esphome"; exit 1; }
	@test -f secrets.yaml || { echo "Missing secrets.yaml. Create it first: cp secrets.yaml.example secrets.yaml"; exit 1; }
	@for file in $(ESPHOME_CONFIGS); do \
		echo "Validating $$file"; \
		esphome config $$file; \
	done

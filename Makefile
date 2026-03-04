.PHONY: test lint clean help

help:  ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test:  ## 运行全部测试
	python3 -m unittest test.test_json_dsl -v

report:  ## 运行测试并生成报告
	python3 -m unittest test.test_json_dsl -v 2>&1 | tee test_report.txt

lint:  ## 语法检查
	python3 -m py_compile src/json_dsl.py
	python3 -m py_compile main.py
	@echo "✅ All files compile successfully"

demo:  ## 运行示例查询
	@echo "── users[age>25].name ──"
	@python3 main.py -d input.json -q 'users[age>25].name'
	@echo ""
	@echo "── users[active==true] | sort(age) | .name ──"
	@python3 main.py -d input.json -q 'users[active==true] | sort(age) | .name'
	@echo ""
	@echo "── users.active ──"
	@python3 main.py -d input.json -q 'users.active'

clean:  ## 清理缓存文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true

bench:  ## 运行性能基准测试
	python3 benchmark.py --size 1000

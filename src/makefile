CXX      = g++
CXXFLAGS = -O2 -std=c++17 -Wall -Wextra
LIBS     = -lmosquitto -lsqlite3 -lpthread
TARGET   = groundeye_orch

.PHONY: all clean deps-fedora deps-debian

all: $(TARGET)

$(TARGET): main.cpp orchestrator.hpp logger.hpp
	$(CXX) $(CXXFLAGS) main.cpp $(LIBS) -o $(TARGET)
	@echo "Derlendi: $(TARGET)"

deps-fedora:
	sudo dnf install -y mosquitto-devel nlohmann-json-devel \
	                    sqlite-devel gcc-c++

deps-debian:
	sudo apt install -y libmosquitto-dev nlohmann-json3-dev \
	                    libsqlite3-dev g++

clean:
	rm -f $(TARGET)

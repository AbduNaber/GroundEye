CXX      = g++
CXXFLAGS = -O2 -std=c++17 -Wall -Wextra
LIBS     = -lmosquitto -lpthread
TARGET   = groundeye_dsp

.PHONY: all clean deps-debian

all: $(TARGET)

$(TARGET): main.cpp dsp.hpp
	$(CXX) $(CXXFLAGS) main.cpp $(LIBS) -o $(TARGET)
	@echo "Derlendi: $(TARGET)"

deps-debian:
	sudo apt install -y libmosquitto-dev nlohmann-json3-dev g++ make

clean:
	rm -f $(TARGET)

